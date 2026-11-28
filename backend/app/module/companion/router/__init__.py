"""Aggregate the companion slice routers."""

from fastapi import APIRouter

from app.module.companion.router.companion_router import router as companion_router

router = APIRouter()
router.include_router(companion_router)

__all__ = ["router"]
