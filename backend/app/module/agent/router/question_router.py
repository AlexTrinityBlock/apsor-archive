"""HTTP adapters for the saved-question Q&A library."""

from fastapi import APIRouter, Depends, Query, Response, status

from app.dependency.auth import get_current_user
from app.module.agent.dependencies import (
    get_saved_question_ask_service,
    get_saved_question_service,
)
from app.module.agent.domain.owner_profile_domain import OwnerProfile
from app.module.agent.schema.saved_question_schema import (
    SavedQuestionCreateSchema,
    SavedQuestionListSchema,
    SavedQuestionReadSchema,
    SavedQuestionUpdateSchema,
)
from app.module.agent.service.saved_question_service import SavedQuestionService
from app.module.auth.schema.auth_schema import UserSchema

router = APIRouter(prefix="/questions", tags=["agent"])


@router.get(
    "",
    response_model=SavedQuestionListSchema,
    operation_id="listSavedQuestions",
)
async def list_saved_questions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    saved_question_service: SavedQuestionService = Depends(get_saved_question_service),
) -> SavedQuestionListSchema:
    """List saved questions newest first with explicit pagination."""
    return await saved_question_service.list_questions(limit=limit, offset=offset)


@router.post(
    "",
    response_model=SavedQuestionReadSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="createSavedQuestion",
)
async def create_saved_question(
    payload: SavedQuestionCreateSchema,
    saved_question_service: SavedQuestionService = Depends(get_saved_question_service),
) -> SavedQuestionReadSchema:
    """Capture a question that can be asked later; the answer starts empty."""
    return await saved_question_service.create_question(payload)


@router.patch(
    "/{question_id}",
    response_model=SavedQuestionReadSchema,
    operation_id="updateSavedQuestion",
)
async def update_saved_question(
    question_id: int,
    payload: SavedQuestionUpdateSchema,
    saved_question_service: SavedQuestionService = Depends(get_saved_question_service),
) -> SavedQuestionReadSchema:
    """Edit the question and clear any answer derived from the old text."""
    return await saved_question_service.update_question(question_id, payload)


@router.delete(
    "/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteSavedQuestion",
)
async def delete_saved_question(
    question_id: int,
    saved_question_service: SavedQuestionService = Depends(get_saved_question_service),
) -> Response:
    """Delete a saved question and its stored answer."""
    await saved_question_service.delete_question(question_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{question_id}/ask",
    response_model=SavedQuestionReadSchema,
    operation_id="askSavedQuestion",
)
async def ask_saved_question(
    question_id: int,
    saved_question_service: SavedQuestionService = Depends(get_saved_question_ask_service),
    user: UserSchema = Depends(get_current_user),
) -> SavedQuestionReadSchema:
    """Run one JSON agent turn and persist its answer, citations, and status.

    A provider/tool failure is returned as HTTP 200 with ``run_status="failed"``
    so the saved question survives; a missing provider configuration still uses
    the existing 503 error envelope.
    """
    return await saved_question_service.ask_question(
        question_id,
        owner_profile=OwnerProfile(
            display_name=user.display_name,
            bio=user.bio,
        ),
    )
