"""Request and response contracts for the saved-question library."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.module.agent.schema.agent_schema import AgentRunStatus


class SavedQuestionCreateSchema(BaseModel):
    """Capture a question without accepting an answer from the client."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=32_000)


class SavedQuestionUpdateSchema(BaseModel):
    """Edit the question text only; answers are written by the agent."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=32_000)


class SavedQuestionReadSchema(BaseModel):
    """A saved question plus its latest ask outcome."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    question: str
    answer: str | None
    citations: list[str]
    conversation_id: int | None
    run_status: AgentRunStatus | None
    error_code: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime
    last_asked_at: datetime | None


class SavedQuestionListSchema(BaseModel):
    """Pagination envelope for the saved-question library."""

    model_config = ConfigDict(frozen=True)

    resources: list[SavedQuestionReadSchema]
    total: int
    limit: int
    offset: int
