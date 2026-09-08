"""FastAPI application entry point.

Run for development from ``backend/``:

    uvicorn sequence_platform.main:app --reload

All routes are mounted under the ``/api`` prefix.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api.routes.alignment import router as alignment_router
from .api.routes.analysis import router as analysis_router
from .api.routes.comparisons import router as comparisons_router
from .api.routes.databases import router as databases_router
from .api.routes.health import router as health_router
from .database.base import SequenceDatabase
from .database.exceptions import (
    AccessionNotFoundError,
    DatabaseError,
    MalformedPayloadError,
    RateLimitedError,
    UnknownDatabaseError,
    UpstreamUnavailableError,
)
from .database.registry import get_database, registered_names

# Origins for the frontend dev server (Vite) during local development.
DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _build_databases() -> dict[str, SequenceDatabase]:
    """Construct one long-lived client per registered provider."""
    return {name: get_database(name) for name in registered_names()}


def _register_exception_handlers(application: FastAPI) -> None:
    """Map every typed ``DatabaseError`` onto an HTTP response.

    Registered once here so routes never hand-map statuses themselves
    (§1 architecture rule: `api/` implements no biology, and no ad hoc
    error handling either).
    """

    @application.exception_handler(AccessionNotFoundError)
    async def _not_found(request: Request, exc: AccessionNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(UnknownDatabaseError)
    async def _unknown_database(
        request: Request, exc: UnknownDatabaseError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(MalformedPayloadError)
    async def _malformed(request: Request, exc: MalformedPayloadError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.exception_handler(RateLimitedError)
    async def _rate_limited(request: Request, exc: RateLimitedError) -> JSONResponse:
        headers = (
            {"Retry-After": str(exc.retry_after)}
            if exc.retry_after is not None
            else None
        )
        return JSONResponse(
            status_code=429, content={"detail": str(exc)}, headers=headers
        )

    @application.exception_handler(UpstreamUnavailableError)
    async def _upstream_unavailable(
        request: Request, exc: UpstreamUnavailableError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @application.exception_handler(DatabaseError)
    async def _database_error(request: Request, exc: DatabaseError) -> JSONResponse:
        # Catch-all for any future DatabaseError subclass that has not
        # been given a specific mapping above.
        return JSONResponse(status_code=502, content={"detail": str(exc)})


def create_app(
    databases: dict[str, SequenceDatabase] | None = None,
) -> FastAPI:
    """Application factory.

    Args:
        databases: Optional pre-built client map, keyed by provider name.
            Tests inject one built with a mocked ``httpx`` transport so no
            real network call is ever made; when omitted, a lifespan
            handler builds one long-lived client per registered provider
            from the current environment at startup and closes them all
            at shutdown.
    """
    injected = databases

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if injected is None:
            app.state.databases = _build_databases()
        try:
            yield
        finally:
            for client in app.state.databases.values():
                await client.close()

    application = FastAPI(
        title="Sequence Platform",
        version=__version__,
        lifespan=lifespan,
    )
    # Set synchronously (not only inside the lifespan) so that any ASGI
    # transport reading `app.state.databases` before the lifespan startup
    # event has run (e.g. httpx.ASGITransport without an explicit
    # `async with LifespanManager`) still sees an injected client map.
    application.state.databases = injected if injected is not None else {}
    application.add_middleware(
        CORSMiddleware,
        allow_origins=DEFAULT_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _register_exception_handlers(application)
    application.include_router(health_router, prefix="/api")
    application.include_router(databases_router, prefix="/api")
    application.include_router(analysis_router, prefix="/api")
    application.include_router(comparisons_router, prefix="/api")
    application.include_router(alignment_router, prefix="/api")
    return application


app = create_app()
