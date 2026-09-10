"""FastAPI application entry point.

Run for development from ``backend/``:

    uvicorn sequence_platform.main:app --reload

All routes are mounted under the ``/api`` prefix.
"""

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from . import __version__
from .api.routes.alignment import router as alignment_router
from .api.routes.analysis import router as analysis_router
from .api.routes.comparisons import router as comparisons_router
from .api.routes.databases import router as databases_router
from .api.routes.exports import router as exports_router
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
from .validation import SequenceValidationError

# Origins for the frontend dev server (Vite) during local development.
DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

#: Root of this application's logger namespace; every module logs below it.
PACKAGE_LOGGER_NAME = "sequence_platform"

#: Format for the application's own records: time, level, logger, message.
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

logger = logging.getLogger(__name__)


def configure_logging(level: int | str = logging.INFO) -> None:
    """Make the application's own log records visible to a deployment.

    Deliberately ``logging.basicConfig``: it is a no-op when the host process
    (uvicorn with ``--log-config``, pytest, an embedding application) has
    already configured the root logger, so this never fights an operator's
    logging setup, and calling it repeatedly cannot stack duplicate handlers.

    The package logger's level is set explicitly because propagation does not
    re-check an ancestor *logger's* level: without it, the INFO records below
    would be dropped under the root logger's default WARNING level, which is
    what uvicorn leaves behind.
    """
    logging.basicConfig(level=level, format=LOG_FORMAT)
    logging.getLogger(PACKAGE_LOGGER_NAME).setLevel(level)


async def _log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Log one access line per request: method, path, status, duration.

    The path only — never the query string, which can carry user input and is
    already represented by the status code in the line.
    """
    started = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "%s %s -> %d in %.1f ms",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000.0,
    )
    return response


def _build_databases() -> dict[str, SequenceDatabase]:
    """Construct one long-lived client per registered provider."""
    return {name: get_database(name) for name in registered_names()}


def _register_exception_handlers(application: FastAPI) -> None:
    """Map every error the lower layers raise onto an HTTP response.

    Covers the typed ``DatabaseError`` hierarchy (404/422/429/503/502), the
    validation layer's ``SequenceValidationError``, the plain ``ValueError``
    that ``analysis/`` raises for caller-contract violations, and a
    last-resort 500 for anything unforeseen.

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

    @application.exception_handler(SequenceValidationError)
    async def _invalid_sequence(
        request: Request, exc: SequenceValidationError
    ) -> JSONResponse:
        # A sequence the platform refuses to accept (empty, wrong alphabet,
        # outside the length bounds) is a request problem, not a server fault.
        # The clients already convert this into MalformedPayloadError before it
        # reaches HTTP, so this handler is the safety net for a future caller
        # that validates a sequence itself.
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.exception_handler(ValueError)
    async def _invalid_request(request: Request, exc: ValueError) -> JSONResponse:
        # ``analysis/`` signals caller-contract violations with a plain
        # ``ValueError`` — k outside the k-mer bounds of the records being
        # compared, or empty inputs to the aligner. Those are the caller's
        # problem (422), and before this handler existed they escaped the app
        # as an unhandled fault. ``analysis/`` itself is untouched: the mapping
        # belongs to the HTTP layer (§1).
        if isinstance(exc, ValidationError):
            # pydantic's ValidationError is a ValueError subclass too; a
            # response-model failure is *our* bug, so re-raise it and let the
            # catch-all below answer with 500 instead of blaming the caller.
            raise exc
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Last resort: the traceback goes to the server log (never to the
        # client) and the caller gets the platform's own JSON error shape
        # instead of Starlette's bare "Internal Server Error" text.
        logger.exception(
            "Unhandled error serving %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=500, content={"detail": "Internal Server Error"}
        )


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
    # CORS policy: the SPA talks to /api through the Vite proxy, so API and UI
    # share an origin in every documented setup; a genuinely cross-origin
    # deployment would need configuration instead of DEFAULT_CORS_ORIGINS
    # (docs/architecture.md §6, Stage 10). Wildcards are deliberately avoided
    # here: combining `allow_origins=["*"]` with `allow_credentials=True` is an
    # invalid pairing.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=DEFAULT_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Registered last, so the access log is the outermost middleware: one line
    # per request, including CORS preflights and requests that never match a
    # route. A request that raises is logged by the 500 handler instead.
    application.middleware("http")(_log_requests)
    _register_exception_handlers(application)
    application.include_router(health_router, prefix="/api")
    application.include_router(databases_router, prefix="/api")
    application.include_router(analysis_router, prefix="/api")
    application.include_router(comparisons_router, prefix="/api")
    application.include_router(alignment_router, prefix="/api")
    application.include_router(exports_router, prefix="/api")
    return application


configure_logging()
logger.info("sequence-platform %s starting", __version__)
app = create_app()
