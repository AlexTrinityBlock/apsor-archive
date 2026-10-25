"""Consumer-owned seam for provider connection tests.

The production implementation builds real infrastructure clients.  Tests can
inject a deterministic fake through ``app.state.provider_tester`` so the test
suite never calls DeepSeek, OpenAI, or Tavily over the network.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.module.knowledge.domain.provider_config_domain import ProviderCapability
from app.module.knowledge.protocol.provider_config import ProviderConfig


class ProviderTestOutcome(BaseModel):
    """A provider test result before the service adds timing metadata."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    detail: str


class ProviderTesterProtocol(Protocol):
    """Perform one small request with an already-resolved provider config."""

    async def test(
        self,
        capability: ProviderCapability,
        config: ProviderConfig,
    ) -> ProviderTestOutcome: ...


__all__ = ["ProviderTestOutcome", "ProviderTesterProtocol"]
