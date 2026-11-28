"""FastAPI application assembly."""

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response

from app.bootstrap import (
    BackgroundServices,
    build_background_services,
    close_process_state,
    open_process_state,
)
from app.dependency.auth import require_authenticated, require_stateless_authenticated
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.database.migrations import upgrade_to_head
from app.infrastructure.logger.logging import configure_logging
from app.module.agent.exception.handler import register_exceptions as register_agent_exceptions
from app.module.agent.repository.agent_repository import AgentRepository
from app.module.agent.router import router as agent_router
from app.module.auth.exception.handler import register_exceptions as register_auth_exceptions
from app.module.auth.router.account_router import router as account_router
from app.module.auth.router.auth_router import router as auth_router
from app.module.companion.exception.handler import (
    register_exceptions as register_companion_exceptions,
)
from app.module.companion.router import router as companion_router
from app.module.knowledge.dependencies import build_job_notifier
from app.module.knowledge.exception.handler import (
    register_exceptions as register_knowledge_exceptions,
)
from app.module.knowledge.router import router as knowledge_router
from app.module.knowledge.router.health_router import router as health_router
from app.module.knowledge.router.ingest_progress_router import (
    router as ingest_progress_router,
)
from app.module.prompt.exception.handler import register_exceptions as register_prompt_exceptions
from app.module.prompt.router import router as prompt_router
from app.module.web_research.exception.handler import (
    register_exceptions as register_web_research_exceptions,
)
from app.shared.exception.registry import ExceptionRegistry
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

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
        resolved_settings.data_dir.mkdir(parents=True, exist_ok=True)
        if resolved_settings.run_migrations:
            await asyncio.to_thread(
                upgrade_to_head,
                resolved_settings.database_url,
            )
        # Alembic's alembic.ini logging config resets the root logger to
        # WARNING. Configure application logging after the migration so INFO
        # request/provider/run logs survive startup.
        configure_logging(debug=resolved_settings.debug)
        # The API always owns the dispatch publisher. A disabled deployment gets
        # the no-op notifier; an enabled deployment without a URL fails here
        # instead of silently advertising a queue it cannot use.
        app.state.job_notifier = build_job_notifier(resolved_settings)
        background: BackgroundServices | None = None
        try:
            await open_process_state(app.state, resolved_settings)
            await AgentRepository.recover_stale_runs(app.state.db, now=utcnow())
            # Production runs ingestion in the dedicated ``apsor-archive worker``
            # process. APSOR_INGEST_WORKER_ENABLED=true is an opt-in
            # single-process development mode that runs the same loops here.
            if resolved_settings.ingest_worker_enabled:
                background = await build_background_services(app.state, resolved_settings)
                app.state.ingest_worker = background.worker
                background.start_worker_loop()
                background.start_side_loops(resolved_settings, None)
                app.state.job_consumer = background.consumer
            yield
        finally:
            if background is not None:
                await background.stop()
            await app.state.job_notifier.close()
            await close_process_state(app.state)

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.version,
        debug=resolved_settings.debug,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )
    app.state.settings = resolved_settings

    register_knowledge_exceptions()
    register_auth_exceptions()
    register_agent_exceptions()
    register_web_research_exceptions()
    register_prompt_exceptions()
    register_companion_exceptions()
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

    @app.middleware("http")
    async def request_logging(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Log API requests with a correlation id and a measured duration.

        Static assets stay at DEBUG so the production log remains readable.
        Query strings are never logged because they can carry user content.
        """
        raw_request_id = (
            request.headers.get("cf-ray")
            or request.headers.get("x-request-id")
            or ""
        )
        request_id = (
            re.sub(r"[^A-Za-z0-9._:-]", "", raw_request_id)[:128]
            or uuid4().hex[:12]
        )
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http request failed method=%s path=%s request_id=%s duration_ms=%d",
                request.method,
                request.url.path,
                request_id,
                int((time.monotonic() - started) * 1000),
            )
            raise
        response.headers["X-Request-ID"] = request_id
        logger.log(
            logging.INFO if request.url.path.startswith("/api/") else logging.DEBUG,
            "http request method=%s path=%s status=%d duration_ms=%d request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            int((time.monotonic() - started) * 1000),
            request_id,
        )
        return response

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(account_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(
        ingest_progress_router,
        prefix="/api/v1",
        # Ingestion progress is SSE. It deliberately stays outside the
        # knowledge aggregate so the request-scoped require_authenticated guard
        # does not hold get_db_session open for the stream's lifetime.
        dependencies=[Depends(require_stateless_authenticated)],
    )
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
    app.include_router(
        companion_router,
        prefix="/api/v1",
        dependencies=[Depends(require_authenticated)],
    )

    @app.get("/health", include_in_schema=False)
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    _mount_spa(app, resolved_settings.static_dir)
    return app


_REVALIDATED_ICONS = frozenset(
    {"favicon.ico", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "site.webmanifest"}
)


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
            if path in _REVALIDATED_ICONS:
                # Revalidate so an icon change reaches returning readers without
                # waiting for the long-lived edge cache used by other files.
                cache = "no-cache, must-revalidate"
            elif path.startswith("assets/"):
                cache = "public, max-age=31536000, immutable"
            else:
                cache = "public, max-age=86400"
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
