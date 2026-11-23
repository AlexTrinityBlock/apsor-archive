"""One-shot connection probe for a chat endpoint assignment.

The probe validates a candidate ``(endpoint row, model, effort)`` triple before
root saves it. It is deliberately independent of the request path: the caller
loads the row and passes the resolved configuration, this module builds one
small client through the factory, performs exactly one non-streaming
generation, and returns a safe outcome. It never touches the database, never
writes anything, and never logs a key or a request body.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.infrastructure.ai.provider_factory import ProviderFactory
from app.module.knowledge.protocol.provider_config import ProviderConfig

logger = logging.getLogger(__name__)

# The design caps a failure detail at 300 characters; it is rendered in a
# settings dialog, not a log line.
_DETAIL_LIMIT = 300
_PROBE_MAX_TOKENS = 16
_DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class ProbeOutcome:
    """A safe result object; ``detail`` never carries credentials."""

    ok: bool
    latency_ms: int
    resolved_model: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    detail: str | None = None


class ProviderProbe:
    """Build one client through the injected factory and test the connection."""

    def __init__(
        self,
        factory: ProviderFactory,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self.factory = factory
        configured_timeout = float(factory.settings.chat_probe_timeout_seconds)
        self.timeout_seconds = (
            float(timeout_seconds) if timeout_seconds is not None else configured_timeout
        )
        if self.timeout_seconds <= 0:
            self.timeout_seconds = _DEFAULT_TIMEOUT_SECONDS

    async def probe(
        self,
        config: ProviderConfig,
        *,
        model: str,
        reasoning_effort: str | None,
    ) -> ProbeOutcome:
        """Test one candidate endpoint/model/effort without persisting anything.

        A candidate config is derived with ``model_copy`` because
        ``ProviderConfig`` is frozen. The factory is the only client source:
        no global runtime, no key lookup, and no database access happen here.
        """
        candidate = config.model_copy(
            update={"model": model, "reasoning_effort": reasoning_effort}
        )
        started = time.perf_counter()
        try:
            generator = self.factory.build_text_generator(candidate)
            probe = getattr(generator, "probe", None)
            if probe is None:
                return self._failure(
                    started,
                    config,
                    "the provider does not support a connection probe",
                )
            completion = await asyncio.wait_for(
                probe(
                    model=model,
                    reasoning_effort=reasoning_effort,
                    max_tokens=_PROBE_MAX_TOKENS,
                ),
                timeout=self.timeout_seconds,
            )
            return ProbeOutcome(
                ok=True,
                latency_ms=_elapsed_ms(started),
                resolved_model=completion.model or None,
                usage=dict(completion.usage),
                detail=None,
            )
        except TimeoutError:
            return self._failure(started, config, "probe timed out")
        except Exception as exc:
            # The error text may contain provider metadata, so it is clipped and
            # the key is redacted before it reaches the response or a log line.
            # Only the exception type is logged: never a key or a request body.
            logger.warning(
                "Provider connection probe failed provider=%s model=%s error_type=%s",
                candidate.provider,
                model or "-",
                type(exc).__name__,
            )
            return self._failure(started, config, _safe_detail(exc, config))

    @staticmethod
    def _failure(
        started: float,
        config: ProviderConfig,
        detail: str,
    ) -> ProbeOutcome:
        return ProbeOutcome(
            ok=False,
            latency_ms=_elapsed_ms(started),
            resolved_model=None,
            usage={},
            detail=_clip(detail, config),
        )


def _safe_detail(exc: BaseException, config: ProviderConfig) -> str:
    """Render one exception for the dialog without credentials or raw bodies."""
    message = str(exc).strip()
    if not message:
        message = type(exc).__name__
    return _clip(message, config)


def _clip(text: str, config: ProviderConfig) -> str:
    """Collapse whitespace, redact the row key, and cap the detail length."""
    message = " ".join(str(text).split())
    if config.api_key:
        message = message.replace(config.api_key, "[redacted]")
    return message[:_DETAIL_LIMIT] or "provider probe failed"


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


__all__ = ["ProbeOutcome", "ProviderProbe"]
