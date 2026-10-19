"""Consumer-owned persistence contract for saved questions."""

from datetime import datetime
from typing import Protocol

from app.module.agent.model.saved_question_model import SavedQuestionModel


class SavedQuestionRepositoryProtocol(Protocol):
    """CRUD plus last-ask persistence on the request transaction."""

    async def add(
        self,
        *,
        question: str,
        now: datetime,
    ) -> SavedQuestionModel: ...

    async def list_questions(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[SavedQuestionModel]: ...

    async def count_questions(self) -> int: ...

    async def get(self, question_id: int) -> SavedQuestionModel | None: ...

    async def update_question(
        self,
        question_id: int,
        *,
        question: str,
        reset_answer: bool,
        now: datetime,
    ) -> SavedQuestionModel | None: ...

    async def delete(self, question_id: int) -> bool: ...

    async def record_ask(
        self,
        question_id: int,
        *,
        answer: str | None,
        citations: list[str],
        conversation_id: int | None,
        run_status: str,
        error_code: str | None,
        error_detail: str | None,
        now: datetime,
    ) -> SavedQuestionModel | None: ...
