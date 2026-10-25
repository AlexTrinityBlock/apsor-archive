"""Consumer-owned view of one active web provider configuration.

This slice deliberately does not import the knowledge slice's ``ProviderConfig``
model. Knowledge's frozen value object satisfies this Protocol structurally,
which keeps the dependency arrow pointing at a contract owned by the consumer
(this slice). Members are read-only properties so a frozen Pydantic model can
satisfy them; ``api_key`` is plaintext only in server memory and must never
reach a response schema, a cache payload, or a log line.
"""

from typing import Protocol


class WebProviderConfigProtocol(Protocol):
    """The minimum configuration a web search/fetch client needs."""

    @property
    def capability(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def base_url(self) -> str | None: ...

    @property
    def api_key(self) -> str | None: ...

    @property
    def enabled(self) -> bool: ...

    @property
    def source(self) -> str: ...
