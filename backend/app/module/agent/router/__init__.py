"""Aggregate the agent slice routers under the API prefix."""

from fastapi import APIRouter

from app.module.agent.router.conversation_router import router as conversation_router
from app.module.agent.router.tool_router import router as tool_router

router = APIRouter(prefix="/agent")
router.include_router(conversation_router)
router.include_router(tool_router)
