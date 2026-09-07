"""Sequence-analysis routes (Stage 4).

Thin endpoints over the pure ``analysis`` layer: each route resolves the
database client from app state (the same lookup as ``routes.databases``),
fetches the record via the injected client, runs the deterministic
functions, and converts the result into a Pydantic schema. No error
mapping here — exceptions propagate to the handlers in ``create_app()``.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ...analysis import quality_control, statistics
from ...database.base import SequenceDatabase
from ...database.exceptions import UnknownDatabaseError
from ...models import SequenceRecord
from ..schemas import QualityReportResponse, SequenceStatisticsResponse

router = APIRouter(prefix="/sequences", tags=["analysis"])


def _get_client(request: Request, name: str) -> SequenceDatabase:
    """Look up the long-lived client for *name* in app state.

    Raises:
        UnknownDatabaseError: no client is registered under *name*; the
            API layer maps it to a 404.
    """
    databases: dict[str, SequenceDatabase] = getattr(request.app.state, "databases", {})
    client = databases.get(name)
    if client is None:
        raise UnknownDatabaseError(name)
    return client


async def _fetch_record(
    request: Request, *, accession: str, database: str
) -> SequenceRecord:
    """Fetch *accession* from the named database (no error handling)."""
    client = _get_client(request, database)
    return await client.fetch(accession)


@router.get("/{accession}/statistics", response_model=SequenceStatisticsResponse)
async def sequence_statistics(
    request: Request,
    accession: str,
    database: str = Query(..., description="Provider name, e.g. 'ncbi'"),
) -> SequenceStatisticsResponse:
    """Deterministic statistics for one fetched record (Stage 4)."""
    record = await _fetch_record(request, accession=accession, database=database)
    return SequenceStatisticsResponse(
        accession=record.accession,
        seq_type=record.seq_type.value,
        length=statistics.sequence_length(record),
        gc_content=statistics.gc_content(record),
        base_composition=statistics.base_composition(record),
        ambiguous_count=statistics.ambiguous_base_count(record),
        ambiguous_percentage=statistics.ambiguous_base_percentage(record),
        n_run_count=statistics.n_run_count(record),
        longest_n_run=statistics.longest_n_run(record),
    )


@router.get("/{accession}/quality", response_model=QualityReportResponse)
async def sequence_quality(
    request: Request,
    accession: str,
    database: str = Query(..., description="Provider name, e.g. 'ncbi'"),
    min_length: int = Query(
        quality_control.DEFAULT_MIN_LENGTH, ge=0, description="Minimum length"
    ),
    max_ambiguous_fraction: float = Query(
        quality_control.DEFAULT_MAX_AMBIGUOUS_FRACTION, ge=0.0, le=1.0
    ),
    max_n_run: int = Query(
        quality_control.DEFAULT_MAX_N_RUN, ge=0, description="Max N-run"
    ),
) -> QualityReportResponse:
    """Threshold-based QC report for one fetched record (Stage 4)."""
    record = await _fetch_record(request, accession=accession, database=database)
    report = quality_control.quality_report(
        record,
        min_length=min_length,
        max_ambiguous_fraction=max_ambiguous_fraction,
        max_n_run=max_n_run,
    )
    return QualityReportResponse(
        accession=record.accession,
        passed=report.passed,
        issues=report.issues,
        min_length=min_length,
        max_ambiguous_fraction=max_ambiguous_fraction,
        max_n_run=max_n_run,
    )
