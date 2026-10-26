"""FastAPI application assembly."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response

from app.dependency.auth import require_authenticated, require_stateless_authenticated
from app.infrastructure.ai.provider_factory import (
    ProviderFactory,
    provider_defaults_from_settings,
)
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.cache.resilient_cache import build_cache
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.database.migrations import upgrade_to_head
from app.infrastructure.database.session import Database, system_session
from app.infrastructure.files.storage_factory import build_file_storage
from app.infrastructure.logger.logging import configure_logging
from app.infrastructure.security.secret_cipher import SecretCipher
from app.module.agent.exception.handler import register_exceptions as register_agent_exceptions
from app.module.agent.repository.agent_repository import AgentRepository
from app.module.agent.router import router as agent_router
from app.module.auth.exception.handler import register_exceptions as register_auth_exceptions
from app.module.auth.router.account_router import router as account_router
from app.module.auth.router.auth_router import router as auth_router
from app.module.knowledge.dependencies import (
    build_ingest_worker,
    ingest_runtime_defaults,
    load_ingest_runtime_config,
)
from app.module.knowledge.exception.handler import register_exceptions
from app.module.knowledge.repository.provider_config_repository import (
    ProviderConfigRepository,
)
from app.module.knowledge.router import router as knowledge_router
from app.module.knowledge.router.health_router import router as health_router
from app.module.prompt.exception.handler import register_prompt_exceptions
from app.module.prompt.router import router as prompt_router
from app.module.web_research.exception.handler import (
    register_exceptions as register_web_research_exceptions,
)
from app.shared.exception.registry import ExceptionRegistry
from app.shared.time import utcnow

_NOT_BUILT = """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Apsor Archive</title></head>
  <body style="font-family: Georgia, serif; max-width: 42rem; margin: 4rem auto">
    <h1>Apsor Archive</h1>
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
        await AgentRepository.recover_stale_runs(app.state.db, now=utcnow())
        app.state.cache = build_cache(resolved_settings.cache_url)
        app.state.storage = build_file_storage(resolved_settings)
        cipher = SecretCipher.from_settings(resolved_settings)
        runtime = AiRuntime(
            builder=ProviderFactory(resolved_settings),
            cipher=cipher,
            defaults=provider_defaults_from_settings(resolved_settings),
        )
        async with system_session(app.state.db.session_factory) as session:
            await runtime.reload(ProviderConfigRepository(session))
        app.state.secret_cipher = cipher
        app.state.ai_runtime = runtime
        ingest_defaults = ingest_runtime_defaults(resolved_settings)
        ingest_config = ingest_defaults
        if resolved_settings.ingest_worker_enabled:
            ingest_config = await load_ingest_runtime_config(
                app.state.db.session_factory,
                ingest_defaults,
            )
        app.state.ingest_worker = build_ingest_worker(
            app.state,
            app.state.db.session_factory,
            resolved_settings,
            runtime_config=ingest_config,
            config_provider=(
                (
                    lambda: load_ingest_runtime_config(
                        app.state.db.session_factory,
                        ingest_defaults,
                    )
                )
                if resolved_settings.ingest_worker_enabled
                else None
            ),
        )
        worker_task: asyncio.Task[None] | None = None
        if resolved_settings.ingest_worker_enabled:
            await app.state.ingest_worker.startup()
            worker_task = asyncio.create_task(
                app.state.ingest_worker.run_forever(),
                name="ingest-worker",
            )
        try:
            yield
        finally:
            if worker_task is not None:
                worker_task.cancel()
                with suppress(asyncio.CancelledError):
                    await worker_task
            app.state.ingest_worker.close()
            await app.state.cache.close()
            await app.state.db.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.version,
        debug=resolved_settings.debug,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )
    app.state.settings = resolved_settings

    register_exceptions()
    register_auth_exceptions()
    register_agent_exceptions()
    register_web_research_exceptions()
    register_prompt_exceptions()
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

    @app.middleware("http")
    async def private_api_cache_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Never let a shared browser reuse authenticated API/download responses.

        File-content handlers set their own ``private`` validator header and are
        left intact; JSON, downloads, auth, and job responses default to no-store.
        """
        response = await call_next(request)
        if (
            request.url.path.startswith("/api/v1/")
            and "cache-control" not in response.headers
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(account_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(
        knowledge_router,
        dependencies=[Depends(require_authenticated)],
    )
    app.include_router(
        agent_router,
        prefix="/api/v1",
        # Agent message/retry routes return SSE. A request-scoped dependency
        # would stay open for the whole stream; route-level guards and the
        # owner-scoped agent repository still enforce authentication and RLS.
        dependencies=[Depends(require_stateless_authenticated)],
    )
    app.include_router(
        prompt_router,
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
        if path.startswith(("api/", "openapi.json")):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        candidate = (resolved / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(resolved):
            cache = (
                "public, max-age=31536000, immutable"
                if path.startswith("assets/")
                else "public, max-age=86400"
            )
            return FileResponse(
                candidate,
                headers={
                    "Cache-Control": cache,
                    "X-Content-Type-Options": "nosniff",
                },
            )
        if not index.is_file():
            return HTMLResponse(_NOT_BUILT, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        return FileResponse(
            index,
            headers={
                "Cache-Control": "no-cache, must-revalidate",
                "X-Content-Type-Options": "nosniff",
            },
        )


app = create_app()
