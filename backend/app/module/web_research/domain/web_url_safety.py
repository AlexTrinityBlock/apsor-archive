"""URL policy for outbound web fetches.

真正發出 HTTP 請求的是 Tavily，不是本服務，所以這裡不是主要的 SSRF 邊界；
它仍是 defense-in-depth：避免 agent 要求第三方爬蟲去探測 loopback、私有網段或
特殊用途位址，也避免把帶帳密或非 http(s) 的 URL 寫進 fetch cache。

所有模組層 helper 都定義在 ``WebUrlSafety`` 之前：若未來出現循環 import，
``WebUrlSafety`` 一旦可被取用，它引用的每個名稱都已存在，不會在 import
尚未完成時呼叫 validate() 而觸發 NameError。
"""

import ipaddress
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.module.web_research.exception.domain_error import WebUrlInvalidError

_MAX_URL_CHARS = 2_048
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost")


def _is_blocked_hostname(host: str) -> bool:
    """Reject loopback names and private-use DNS suffixes."""
    lowered = host.lower()
    if lowered == "localhost":
        return True
    if lowered in {"local", "internal"}:
        return True
    return lowered.endswith(_BLOCKED_HOST_SUFFIXES)


def _parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _looks_like_legacy_ipv4(host: str) -> bool:
    """Detect numeric IPv4 spellings that ``ipaddress`` rejects.

    只檢查「全部由數字（或 0x 十六進位）組成、以點分隔、最多四段」的 host；
    一般網域至少會有一段含非數字字元，因此不會被誤擋。
    """
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return False
    for part in parts:
        value = part.lower()
        if value.startswith("0x"):
            digits = value[2:]
            if not digits or any(character not in "0123456789abcdef" for character in digits):
                return False
        elif not value.isdigit():
            return False
    return True


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return ``True`` only for globally routable unicast addresses.

    Python 3.13 對 multicast 位址回報 ``is_global=True``（例如 224.0.0.1、
    ff02::1），因此不能只靠 ``is_global``；逐一檢查規格列出的類別，再要求
    ``is_global``，可同時擋掉 CGNAT 100.64/10 等非公開特殊網段。
    IPv4-mapped IPv6（::ffff:127.0.0.1）要拆出內嵌的 IPv4 再判斷，否則會被
    當成一般 IPv6 位址而漏檢。
    """
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        return _is_public_address(mapped)
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return False
    return address.is_global


class WebUrlSafety:
    """Pure, stateless URL validation and normalization."""

    @staticmethod
    def validate(url: str) -> str:
        """Return a normalized URL or raise :class:`WebUrlInvalidError`.

        Normalization 是 cache 正確性的前提：同一個資源的不同寫法（大小寫、
        預設 port、空 path、fragment）必須收斂成同一個字串，fetch cache key
        才會穩定；fragment 不會送給伺服器，一律移除。
        """
        raw = url.strip()
        if not raw or len(raw) > _MAX_URL_CHARS:
            raise WebUrlInvalidError("URL must contain 1 to 2048 characters.")
        # 控制字元與空白可能讓不同解析器得到不同 host（browser vs urllib），
        # 直接拒絕，避免同一字串在兩層之間出現解讀落差。
        if any(character.isspace() or ord(character) < 0x20 for character in raw):
            raise WebUrlInvalidError("URL must not contain whitespace or control characters.")

        try:
            parts = urlsplit(raw)
        except ValueError as exc:
            raise WebUrlInvalidError("URL could not be parsed.") from exc

        scheme = parts.scheme.lower()
        if scheme not in _ALLOWED_SCHEMES:
            raise WebUrlInvalidError("Only http and https URLs are allowed.")
        # 使用者名稱／密碼會出現在 provider 記錄與錯誤訊息中，且對抓取沒有用途。
        if parts.username is not None or parts.password is not None:
            raise WebUrlInvalidError("URLs must not contain credentials.")

        host = parts.hostname
        if not host:
            raise WebUrlInvalidError("URL must include a hostname.")
        # urlsplit 已將 hostname 轉為小寫；DNS 尾端點號（example.com.）與
        # 無點寫法等價，先移除再判斷保留網域，避免 `localhost.` 之類的繞過。
        normalized_host = host.rstrip(".")
        if not normalized_host:
            raise WebUrlInvalidError("URL must include a hostname.")
        if _is_blocked_hostname(normalized_host):
            raise WebUrlInvalidError("URL host is not reachable from the public internet.")
        address = _parse_ip_literal(normalized_host)
        if address is not None and not _is_public_address(address):
            raise WebUrlInvalidError("URL host is a private or special-use address.")
        # 瀏覽器與 inet_aton 接受 127.1、0x7f000001、2130706433 等舊式 IPv4 寫法，
        # ipaddress 卻不認；若放行，Tavily 仍可能解析到 loopback。
        if address is None and _looks_like_legacy_ipv4(normalized_host):
            raise WebUrlInvalidError("URL host is a private or special-use address.")

        try:
            port = parts.port
        except ValueError as exc:
            raise WebUrlInvalidError("URL port is invalid.") from exc
        # 預設 port 省略，讓 `https://example.com` 與 `https://example.com:443`
        # 產生同一個 cache key。
        if port is not None and port == (80 if scheme == "http" else 443):
            port = None

        netloc = f"[{normalized_host}]" if ":" in normalized_host else normalized_host
        if port is not None:
            netloc = f"{netloc}:{port}"
        return urlunsplit(
            SplitResult(
                scheme=scheme,
                netloc=netloc,
                path=parts.path or "/",
                query=parts.query,
                fragment="",
            )
        )
