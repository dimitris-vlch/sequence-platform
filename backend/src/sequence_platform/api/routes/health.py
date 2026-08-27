"""Health endpoint used by the frontend and CI smoke checks."""

from datetime import UTC, datetime

from fastapi import APIRouter

from ... import __version__
from ...database.registry import SUPPORTED_DATABASES

router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    """Report service liveness and version."""
    return {
        "ok": True,
        "service": "sequence-platform",
        "version": __version__,
        "time": datetime.now(UTC).isoformat(),
        "databases": SUPPORTED_DATABASES,
    }
