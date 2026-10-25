"""Aggregate the prompt slice routers under the API prefix."""

from fastapi import APIRouter

from app.module.prompt.router.frequent_prompt_router import router as frequent_prompt_router

router = APIRouter()
router.include_router(frequent_prompt_router)

__all__ = ["router"]
