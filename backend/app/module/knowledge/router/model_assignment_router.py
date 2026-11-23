"""HTTP adapters for account model assignments and chat endpoint discovery.

Every write is root-only and applies ``require_root`` per route rather than on
the router, because ``/model-assignments/me`` must stay available to every
authenticated account. ``/me`` is declared before the ``/{user_id}`` routes.
"""

from fastapi import APIRouter, Depends

from app.dependency.auth import require_authenticated, require_root
from app.module.auth.schema.auth_schema import UserSchema
from app.module.knowledge.dependencies import get_model_assignment_service
from app.module.knowledge.schema.model_assignment_schema import (
    ChatEndpointListSchema,
    ChatEndpointProbeResultSchema,
    ChatEndpointProbeSchema,
    ModelAssignmentListSchema,
    ModelAssignmentSchema,
    ModelAssignmentUpdateSchema,
    ModelCatalogListSchema,
)
from app.module.knowledge.service.model_assignment_service import (
    ModelAssignmentService,
)

router = APIRouter(tags=["model-assignments"])


@router.get(
    "/model-assignments",
    response_model=ModelAssignmentListSchema,
    operation_id="listModelAssignments",
)
async def list_model_assignments(
    _user: UserSchema = Depends(require_root),
    service: ModelAssignmentService = Depends(get_model_assignment_service),
) -> ModelAssignmentListSchema:
    """Return every account assignment for the root Accounts page."""
    return await service.list_assignments()


@router.get(
    "/model-assignments/me",
    response_model=ModelAssignmentSchema,
    operation_id="getMyModelAssignment",
)
async def get_my_model_assignment(
    user: UserSchema = Depends(require_authenticated),
    service: ModelAssignmentService = Depends(get_model_assignment_service),
) -> ModelAssignmentSchema:
    """Return the caller's own read-only assignment view."""
    return await service.get_my_assignment(user.user_id)


@router.put(
    "/model-assignments/{user_id}",
    response_model=ModelAssignmentSchema,
    operation_id="updateModelAssignment",
)
async def update_model_assignment(
    user_id: int,
    payload: ModelAssignmentUpdateSchema,
    _user: UserSchema = Depends(require_root),
    service: ModelAssignmentService = Depends(get_model_assignment_service),
) -> ModelAssignmentSchema:
    """Validate both endpoints, probe changed slots, and save both assignments."""
    return await service.update_assignment(user_id, payload)


@router.delete(
    "/model-assignments/{user_id}",
    response_model=ModelAssignmentSchema,
    operation_id="resetModelAssignment",
)
async def reset_model_assignment(
    user_id: int,
    _user: UserSchema = Depends(require_root),
    service: ModelAssignmentService = Depends(get_model_assignment_service),
) -> ModelAssignmentSchema:
    """Clear both assignments, leaving the account unassigned."""
    return await service.reset_assignment(user_id)


@router.get(
    "/chat-endpoints",
    response_model=ChatEndpointListSchema,
    operation_id="listChatEndpoints",
)
async def list_chat_endpoints(
    _user: UserSchema = Depends(require_root),
    service: ModelAssignmentService = Depends(get_model_assignment_service),
) -> ChatEndpointListSchema:
    """List saved chat rows for the assignment dialog, host names only."""
    return await service.list_chat_endpoints()


@router.post(
    "/chat-endpoints/{provider_config_id}/probe",
    response_model=ChatEndpointProbeResultSchema,
    operation_id="probeChatEndpoint",
)
async def probe_chat_endpoint(
    provider_config_id: int,
    payload: ChatEndpointProbeSchema,
    _user: UserSchema = Depends(require_root),
    service: ModelAssignmentService = Depends(get_model_assignment_service),
) -> ChatEndpointProbeResultSchema:
    """Test one candidate model/effort; writes nothing and never returns a 500."""
    return await service.probe_chat_endpoint(provider_config_id, payload)


@router.get(
    "/model-catalog",
    response_model=ModelCatalogListSchema,
    operation_id="listChatModels",
)
async def list_chat_models(
    _user: UserSchema = Depends(require_root),
    service: ModelAssignmentService = Depends(get_model_assignment_service),
) -> ModelCatalogListSchema:
    """Return the advisory model catalog; any other model string is legal."""
    return await service.list_chat_models()


__all__ = ["router"]
