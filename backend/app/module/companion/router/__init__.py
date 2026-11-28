"""Aggregate the companion slice routers."""

from fastapi import APIRouter

from app.module.companion.router.companion_router import router as companion_router
from app.module.companion.router.companion_story_router import router as story_router

router = APIRouter()
# Story routes first: the literal ``stories`` segment must not reach the
# integer ``/{companion_id}`` routes.
router.include_router(story_router)
router.include_router(companion_router)

__all__ = ["router"]
