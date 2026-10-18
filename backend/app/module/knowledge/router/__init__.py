"""Aggregate the knowledge slice routers under the API prefix."""

from fastapi import APIRouter

from app.module.knowledge.router.ai_router import router as ai_router
from app.module.knowledge.router.file_router import router as file_router
from app.module.knowledge.router.memory_router import router as memory_router
from app.module.knowledge.router.search_router import router as search_router
from app.module.knowledge.router.settings_router import router as settings_router
from app.module.knowledge.router.system_router import router as system_router
from app.module.knowledge.router.timeline_router import router as timeline_router
from app.module.knowledge.router.tool_router import router as tool_router
from app.module.knowledge.router.tree_router import router as tree_router

router = APIRouter(prefix="/api/v1")
router.include_router(search_router)
router.include_router(file_router)
router.include_router(tree_router)
router.include_router(memory_router)
router.include_router(timeline_router)
router.include_router(ai_router)
router.include_router(system_router)
router.include_router(settings_router)
router.include_router(tool_router)
