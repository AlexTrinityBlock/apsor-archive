"""Persistence contract for the four provider capability tables."""

from collections.abc import Sequence
from typing import Protocol

from app.module.knowledge.domain.provider_config_domain import ProviderTableSpec
from app.module.knowledge.model.provider_config_model import ProviderConfigMixin


class ProviderConfigRepositoryProtocol(Protocol):
    """One generic API over four physical tables selected by ``ProviderTableSpec``."""

    async def flush(self) -> None: ...

    async def get_by_id(
        self,
        spec: ProviderTableSpec,
        provider_id: int,
    ) -> ProviderConfigMixin | None: ...

    async def get_active(self, spec: ProviderTableSpec) -> ProviderConfigMixin | None: ...

    async def list_all(self, spec: ProviderTableSpec) -> Sequence[ProviderConfigMixin]: ...

    async def list_active(self) -> Sequence[ProviderConfigMixin]: ...

    async def save(self, row: ProviderConfigMixin) -> ProviderConfigMixin: ...

    async def delete(self, row: ProviderConfigMixin) -> None: ...

    async def deactivate_all(self, spec: ProviderTableSpec) -> None: ...

    async def deactivate_others(
        self,
        spec: ProviderTableSpec,
        *,
        keep_id: int,
    ) -> None: ...


__all__ = ["ProviderConfigRepositoryProtocol"]
