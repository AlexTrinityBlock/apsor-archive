"""Port for the deployment's default chat endpoint.

The auth slice creates accounts but must not read the knowledge slice's
provider tables directly. The composition root supplies an adapter, and the
account service only sees this narrow contract.
"""

from typing import Protocol


class ChatDefaultsProtocol(Protocol):
    """Resolve the assignment a newly created account inherits."""

    async def primary_endpoint(self) -> tuple[int, str] | None:
        """Return ``(provider_config_id, model)`` or ``None`` when unavailable.

        The implementation chooses the deployment's active primary chat row in
        ``(priority, id)`` order. A keyless row is still a valid default because
        the runtime resolves the provider-scoped environment key for it.
        """
        ...
