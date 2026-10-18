"""FastAPI application assembly."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from app.dependency.auth import require_authenticated
from app.infrastructure.ai.provider_factory import (
    ProviderFactory,
    provider_defaults_from_settings,
)
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.cache.resilient_cache import build_cache
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.database.migrations import upgrade_to_head
from app.infrastructure.database.session import Database
from app.infrastructure.files.local_storage import LocalFileStorage
from app.infrastructure.logger.logging import configure_logging
from app.infrastructure.security.secret_cipher import SecretCipher
from app.module.agent.exception.handler import register_exceptions as register_agent_exceptions
from app.module.agent.repository.agent_repository import AgentRepository
from app.module.agent.router import router as agent_router
from app.module.auth.exception.handler import register_exceptions as register_auth_exceptions
from app.module.auth.router.auth_router import router as auth_router
from app.module.knowledge.exception.handler import register_exceptions
from app.module.knowledge.repository.ai_config_repository import AiProviderConfigRepository
from app.module.knowledge.router import router as knowledge_router
from app.module.knowledge.router.health_router import router as health_router
from app.module.media.exception.handler import register_exceptions as register_media_exceptions
from app.module.media.router.media_router import router as media_router
from app.shared.exception.registry import ExceptionRegistry
from app.shared.time import utcnow

_NOT_BUILT = """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>DendroMatrix</title></head>
  <body style="font-family: Georgia, serif; max-width: 42rem; margin: 4rem auto">
    <h1>DendroMatrix</h1>
    <p>The API is running, but the web client has not been built yet.</p>
    <pre>cd frontend &amp;&amp; bun install &amp;&amp; bun run build</pre>
    <p>The OpenAPI docs live at <a href="/docs">/docs</a>.</p>
  </body>
</html>
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API application, including its request-scoped resources."""
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(debug=resolved_settings.debug)
        resolved_settings.data_dir.mkdir(parents=True, exist_ok=True)
        if resolved_settings.run_migrations:
            await asyncio.to_thread(
                upgrade_to_head,
                resolved_settings.database_url,
            )
        app.state.db = Database(
            resolved_settings.database_url,
            echo=resolved_settings.debug,
        )
        await AgentRepository(app.state.db.session_factory).mark_interrupted_runs(
            now=utcnow()
        )
        app.state.cache = build_cache(resolved_settings.cache_url)
        app.state.storage = LocalFileStorage(resolved_settings.data_dir)
        cipher = SecretCipher.from_settings(resolved_settings)
        runtime = AiRuntime(
            builder=ProviderFactory(resolved_settings),
            cipher=cipher,
            defaults=provider_defaults_from_settings(resolved_settings),
        )
        async with app.state.db.session_factory() as session:
            await runtime.reload(AiProviderConfigRepository(session))
        app.state.secret_cipher = cipher
        app.state.ai_runtime = runtime
        try:
            yield
        finally:
            await app.state.cache.close()
            await app.state.db.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.version,
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings

    register_exceptions()
    register_media_exceptions()
    register_auth_exceptions()
    register_agent_exceptions()
    ExceptionRegistry.setup_app(app)

    if resolved_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved_settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(
        GZipMiddleware,
        minimum_size=resolved_settings.gzip_minimum_size,
    )

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(
        knowledge_router,
        dependencies=[Depends(require_authenticated)],
    )
    app.include_router(
        media_router,
        prefix="/api/v1",
        dependencies=[Depends(require_authenticated)],
    )
    app.include_router(
        agent_router,
        prefix="/api/v1",
        dependencies=[Depends(require_authenticated)],
    )

    @app.get("/health", include_in_schema=False)
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    _mount_spa(app, resolved_settings.static_dir)
    return app


def _mount_spa(app: FastAPI, directory: Path) -> None:
    """Serve the committed Vite build, with API routes winning first."""
    resolved = directory.resolve()
    index = resolved / "index.html"

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    def spa(path: str) -> FileResponse | HTMLResponse:
        if path.startswith(("api/", "docs", "openapi.json", "redoc")):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        candidate = (resolved / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(resolved):
            return FileResponse(candidate)
        if not index.is_file():
            return HTMLResponse(_NOT_BUILT, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        return FileResponse(index)


app = create_app()
