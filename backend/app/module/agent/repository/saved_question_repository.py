"""SQLAlchemy persistence for the saved-question library.

The repository uses the request-scoped ``AsyncSession`` injected by the
composition root. Asking a saved question is a JSON request, not an SSE stream,
so this service may keep its transaction open while the agent runs. The agent
loop itself still opens its own short-lived sessions.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.agent.model.saved_question_model import SavedQuestionModel


class SavedQuestionRepository:
    """Request-transaction CRUD for saved questions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        question: str,
        now: datetime,
    ) -> SavedQuestionModel:
        saved_question = SavedQuestionModel(
            question=question,
            answer=None,
            citations=[],
            conversation_id=None,
            run_status=None,
            error_code=None,
            error_detail=None,
            created_at=now,
            updated_at=now,
            last_asked_at=None,
        )
        self.session.add(saved_question)
        await self.session.flush()
        return saved_question

    async def list_questions(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[SavedQuestionModel]:
        statement = (
            select(SavedQuestionModel)
            .order_by(SavedQuestionModel.created_at.desc(), SavedQuestionModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def count_questions(self) -> int:
        statement = select(func.count()).select_from(SavedQuestionModel)
        return int((await self.session.execute(statement)).scalar_one())

    async def get(self, question_id: int) -> SavedQuestionModel | None:
        return await self.session.get(SavedQuestionModel, question_id)

    async def update_question(
        self,
        question_id: int,
        *,
        question: str,
        reset_answer: bool,
        now: datetime,
    ) -> SavedQuestionModel | None:
        saved_question = await self.session.get(SavedQuestionModel, question_id)
        if saved_question is None:
            return None
        saved_question.question = question
        if reset_answer:
            saved_question.answer = None
            saved_question.citations = []
            saved_question.conversation_id = None
            saved_question.run_status = None
            saved_question.error_code = None
            saved_question.error_detail = None
            saved_question.last_asked_at = None
        saved_question.updated_at = now
        await self.session.flush()
        return saved_question

    async def delete(self, question_id: int) -> bool:
        saved_question = await self.session.get(SavedQuestionModel, question_id)
        if saved_question is None:
            return False
        await self.session.delete(saved_question)
        await self.session.flush()
        return True

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
    ) -> SavedQuestionModel | None:
        saved_question = await self.session.get(SavedQuestionModel, question_id)
        if saved_question is None:
            return None
        saved_question.answer = answer
        saved_question.citations = citations
        saved_question.conversation_id = conversation_id
        saved_question.run_status = run_status
        saved_question.error_code = error_code
        saved_question.error_detail = error_detail
        saved_question.last_asked_at = now
        saved_question.updated_at = now
        await self.session.flush()
        return saved_question
