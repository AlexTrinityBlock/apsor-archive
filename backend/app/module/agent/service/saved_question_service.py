"""Saved-question CRUD and ask orchestration.

Asking a saved question creates a fresh agent conversation, runs exactly one
turn through ``AgentService``, and writes the outcome back to the same saved
question row. A failed turn keeps the row (and its question) and records the
failure metadata instead of deleting it.
"""

from app.module.agent.domain.owner_profile_domain import OwnerProfile
from app.module.agent.exception.domain_error import (
    AgentNotConfiguredError,
    SavedQuestionNotFoundError,
)
from app.module.agent.model.saved_question_model import SavedQuestionModel
from app.module.agent.protocol.saved_question_repository_protocol import (
    SavedQuestionRepositoryProtocol,
)
from app.module.agent.schema.agent_schema import (
    AgentConversationCreateSchema,
    AgentEntrySchema,
    AgentMessageCreateSchema,
)
from app.module.agent.schema.saved_question_schema import (
    SavedQuestionCreateSchema,
    SavedQuestionListSchema,
    SavedQuestionReadSchema,
    SavedQuestionUpdateSchema,
)
from app.module.agent.service.agent_service import AgentService
from app.shared.time import utcnow

TITLE_MAX_CHARS = 80


class SavedQuestionService:
    """Own validation, edit/reset semantics, and the ask orchestration."""

    def __init__(
        self,
        *,
        repository: SavedQuestionRepositoryProtocol,
        agent_service: AgentService | None = None,
    ) -> None:
        self.repository = repository
        self.agent_service = agent_service

    async def list_questions(
        self,
        *,
        limit: int,
        offset: int,
    ) -> SavedQuestionListSchema:
        rows = await self.repository.list_questions(limit=limit, offset=offset)
        total = await self.repository.count_questions()
        return SavedQuestionListSchema(
            resources=[_read_schema(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def create_question(
        self,
        payload: SavedQuestionCreateSchema,
    ) -> SavedQuestionReadSchema:
        question = _normalize_question(payload.question)
        row = await self.repository.add(question=question, now=utcnow())
        return _read_schema(row)

    async def update_question(
        self,
        question_id: int,
        payload: SavedQuestionUpdateSchema,
    ) -> SavedQuestionReadSchema:
        current = await self.repository.get(question_id)
        if current is None:
            raise SavedQuestionNotFoundError(question_id)
        question = _normalize_question(payload.question)
        # Editing the text invalidates every answer-derived field. This includes
        # the conversation link so the UI cannot present an answer that belongs
        # to a different question. An unchanged edit only refreshes updated_at.
        reset_answer = question != current.question
        row = await self.repository.update_question(
            question_id,
            question=question,
            reset_answer=reset_answer,
            now=utcnow(),
        )
        if row is None:
            raise SavedQuestionNotFoundError(question_id)
        return _read_schema(row)

    async def delete_question(self, question_id: int) -> None:
        deleted = await self.repository.delete(question_id)
        if not deleted:
            raise SavedQuestionNotFoundError(question_id)

    async def ask_question(
        self,
        question_id: int,
        *,
        owner_profile: OwnerProfile | None = None,
    ) -> SavedQuestionReadSchema:
        """Run one agent turn for an existing saved question.

        The saved row is created before this endpoint is called, so the
        conversation count grows by one per ask while the saved-question count
        stays unchanged.
        """
        saved_question = await self.repository.get(question_id)
        if saved_question is None:
            raise SavedQuestionNotFoundError(question_id)
        if self.agent_service is None:
            raise AgentNotConfiguredError()

        conversation = await self.agent_service.create_conversation(
            AgentConversationCreateSchema(title=_conversation_title(saved_question.question)),
            owner_profile=owner_profile,
        )
        turn = await self.agent_service.begin_message(
            conversation.id,
            AgentMessageCreateSchema(content=saved_question.question),
        )
        result = await self.agent_service.collect_turn(turn)
        row = await self.repository.record_ask(
            question_id,
            answer=result.answer,
            citations=_citations_from(result.assistant_entry),
            conversation_id=conversation.id,
            run_status=result.run.status,
            error_code=result.error_code,
            error_detail=result.error_detail,
            now=utcnow(),
        )
        if row is None:
            raise SavedQuestionNotFoundError(question_id)
        return _read_schema(row)


def _normalize_question(question: str) -> str:
    return question.strip()


def _conversation_title(question: str) -> str:
    title = " ".join(question.split())[:TITLE_MAX_CHARS].strip()
    return title or "Saved question"


def _citations_from(assistant_entry: AgentEntrySchema | None) -> list[str]:
    """Read citation tokens from the final assistant entry's UI data."""
    if assistant_entry is None or not isinstance(assistant_entry.data, dict):
        return []
    value = assistant_entry.data.get("citations")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _read_schema(row: SavedQuestionModel) -> SavedQuestionReadSchema:
    return SavedQuestionReadSchema.model_validate(row)
