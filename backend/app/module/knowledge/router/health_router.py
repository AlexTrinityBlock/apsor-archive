"""Public health endpoint for the container healthcheck and the login gate."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.database.session import get_db_session
from app.module.knowledge.dependencies import (
    get_ai_runtime,
    get_cache,
    get_text_generator,
)
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
from app.module.knowledge.schema.system_schema import HealthSchema

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthSchema, operation_id="getHealth")
async def get_health(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    cache: CacheProtocol = Depends(get_cache),
    text_generator: TextGeneratorProtocol = Depends(get_text_generator),
    ai_runtime: AiRuntime = Depends(get_ai_runtime),
) -> HealthSchema | JSONResponse:
    """Check the database, cache, and AI configuration without leaking secrets."""
    try:
        await session.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:
        database_status = "error"
    cache_status = "ok" if await cache.ping() else "degraded"
    settings = request.app.state.settings
    payload = HealthSchema(
        status="ok" if database_status == "ok" else "degraded",
        version=settings.version,
        database=database_status,
        cache=cache_status,
        ai="configured" if text_generator.configured else "missing",
        embedding_provider=ai_runtime.embedding_config.provider,
    )
    if database_status != "ok":
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))
    return payload
