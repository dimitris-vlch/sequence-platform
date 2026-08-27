"""FastAPI application entry point.

Run for development from ``backend/``:

    uvicorn sequence_platform.main:app --reload

All routes are mounted under the ``/api`` prefix.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.routes.health import router as health_router

# Origins for the frontend dev server (Vite) during local development.
DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app() -> FastAPI:
    """Application factory, kept trivial in Stage 1."""
    application = FastAPI(
        title="Sequence Platform",
        version=__version__,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=DEFAULT_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router, prefix="/api")
    return application


app = create_app()
