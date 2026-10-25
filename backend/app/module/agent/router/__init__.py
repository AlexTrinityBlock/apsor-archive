"""Aggregate the agent slice routers under the API prefix."""

from fastapi import APIRouter

from app.module.agent.router.approval_router import router as approval_router
from app.module.agent.router.conversation_router import router as conversation_router
from app.module.agent.router.question_router import router as question_router
from app.module.agent.router.settings_router import router as settings_router
from app.module.agent.router.system_prompt_router import router as system_prompt_router
from app.module.agent.router.tool_router import router as tool_router

router = APIRouter(prefix="/agent")
router.include_router(approval_router)
router.include_router(conversation_router)
router.include_router(question_router)
router.include_router(settings_router)
router.include_router(system_prompt_router)
router.include_router(tool_router)
