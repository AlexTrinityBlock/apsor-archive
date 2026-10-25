"""Read, replace, and reset the singleton custom system prompt."""

from app.module.agent.domain.system_prompt_domain import SystemPromptText
from app.module.agent.exception.domain_error import AgentInvalidSystemPromptError
from app.module.agent.protocol.system_prompt_repository_protocol import (
    SystemPromptRepositoryProtocol,
)
from app.module.agent.schema.system_prompt_schema import (
    SystemPromptReadSchema,
    SystemPromptUpdateSchema,
)
from app.shared.time import utcnow


class SystemPromptService:
    """Keep the owner-authored prompt small, trimmed, and easy to reset."""

    def __init__(self, repository: SystemPromptRepositoryProtocol) -> None:
        self.repository = repository

    async def get_prompt(self) -> SystemPromptReadSchema:
        record = await self.repository.get()
        return _read_schema(record)

    async def get_active(self) -> SystemPromptText | None:
        """Return the prompt only when it has a non-empty body."""
        record = await self.repository.get()
        if record is None or not record.body.strip():
            return None
        return SystemPromptText(
            title=record.title.strip() or "System prompt",
            body=record.body.strip(),
            updated_at=record.updated_at,
        )

    async def update_prompt(self, payload: SystemPromptUpdateSchema) -> SystemPromptReadSchema:
        title = payload.title.strip()
        body = payload.body.strip()
        if not title:
            raise AgentInvalidSystemPromptError("A system prompt title is required.")
        if not body:
            raise AgentInvalidSystemPromptError("A system prompt body is required.")
        record = await self.repository.save(title=title, body=body, now=utcnow())
        return _read_schema(record)

    async def reset_prompt(self) -> SystemPromptReadSchema:
        await self.repository.clear()
        return _read_schema(None)


def _read_schema(record: SystemPromptText | None) -> SystemPromptReadSchema:
    if record is None or not record.body.strip():
        return SystemPromptReadSchema(
            title=record.title if record is not None else "",
            body=record.body if record is not None else "",
            is_custom=False,
            updated_at=record.updated_at if record is not None else None,
        )
    return SystemPromptReadSchema(
        title=record.title,
        body=record.body,
        is_custom=True,
        updated_at=record.updated_at,
    )
