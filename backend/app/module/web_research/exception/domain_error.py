"""Domain errors for the web research slice.

錯誤訊息會經由全域 envelope 回到呼叫端（agent tool 或 HTTP），因此這裡的
字串**不得**包含 API key、Authorization header 或 provider 回應的原始標頭。
金鑰只存在 server 記憶體與 Tavily 請求的 header 中。
"""


class WebResearchError(Exception):
    """Base class for every web-research failure."""


class WebSearchNotConfiguredError(WebResearchError):
    def __init__(self) -> None:
        super().__init__("No web search provider is configured for this instance.")


class WebFetchNotConfiguredError(WebResearchError):
    def __init__(self) -> None:
        super().__init__("No web fetch provider is configured for this instance.")


class WebUrlInvalidError(WebResearchError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class WebProviderAuthenticationError(WebResearchError):
    def __init__(self, provider: str, status_code: int) -> None:
        # 只帶 provider 名稱與狀態碼；不轉貼 provider 回應，避免任何 header 或
        # 金鑰片段跟著例外訊息外流。
        super().__init__(f"The {provider} provider rejected the API key (HTTP {status_code}).")


class WebProviderError(WebResearchError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"The web provider failed: {detail}")
