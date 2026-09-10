"""Pairwise sequence alignment route (Stage 6) — ``GET /api/align``.

Fetches two sequences from the selected database (or a single accession
to align a record against itself) and returns the Stage 6 alignment
result — score, gapped sequences, and coordinates. The alignment itself
lives in the pure ``analysis`` package; this route only wires HTTP to it.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ...analysis.alignment import global_alignment, local_alignment
from ...database.base import SequenceDatabase
from ...database.exceptions import UnknownDatabaseError
from ...models import SequenceRecord
from ..schemas import AlignmentResponse

router = APIRouter(prefix="/align", tags=["align"])


def _get_client(request: Request, name: str | None) -> SequenceDatabase:
    """Look up the long-lived client for *name* in app state.

    An empty/omitted name defaults to the NCBI client.

    Raises:
        UnknownDatabaseError: no client is registered under *name*; the
            API layer maps it to a 404.
    """
    key = "ncbi" if not name else name
    databases: dict[str, SequenceDatabase] = getattr(request.app.state, "databases", {})
    client = databases.get(key)
    if client is None:
        raise UnknownDatabaseError(key)
    return client


def alignment_response(
    record_a: SequenceRecord,
    record_b: SequenceRecord,
    *,
    mode: str,
    match_score: float,
    mismatch_score: float,
    open_gap_score: float,
    extend_gap_score: float,
) -> AlignmentResponse:
    """Build the Stage 6 alignment schema for two fetched records.

    Shared with the Stage 9 export routes, so an exported alignment and the
    ``/api/align`` response can never differ.
    """
    if mode == "local":
        result = local_alignment(
            record_a,
            record_b,
            match_score=match_score,
            mismatch_score=mismatch_score,
            open_gap_score=open_gap_score,
            extend_gap_score=extend_gap_score,
        )
    else:
        result = global_alignment(
            record_a,
            record_b,
            match_score=match_score,
            mismatch_score=mismatch_score,
            open_gap_score=open_gap_score,
            extend_gap_score=extend_gap_score,
        )
    return AlignmentResponse(
        accession_a=record_a.accession,
        accession_b=record_b.accession,
        mode=mode,
        score=result.score,
        aligned_a=result.aligned_a,
        aligned_b=result.aligned_b,
        start_a=result.start_a,
        end_a=result.end_a,
        start_b=result.start_b,
        end_b=result.end_b,
        match_score=match_score,
        mismatch_score=mismatch_score,
        open_gap_score=open_gap_score,
        extend_gap_score=extend_gap_score,
    )


@router.get("", response_model=AlignmentResponse)
async def align_sequences(
    request: Request,
    accession_a: str = Query(
        min_length=1, description="Accession of the first sequence"
    ),
    accession_b: str = Query(
        default="",
        description="Accession of the second sequence; empty aligns A against itself",
    ),
    database: str | None = Query(
        default=None, description="Database name to fetch from (default ncbi)"
    ),
    mode: str = Query(
        default="global",
        pattern="^(global|local)$",
        description="Alignment mode: 'global' (Needleman-Wunsch) or 'local' (Smith-Waterman)",
    ),
    match_score: float = Query(default=1.0, description="Score for a matching pair"),
    mismatch_score: float = Query(
        default=-1.0, description="Score for a mismatching pair"
    ),
    open_gap_score: float = Query(
        default=-2.0, description="Penalty for opening a gap"
    ),
    extend_gap_score: float = Query(
        default=-0.5, description="Penalty for extending a gap"
    ),
) -> AlignmentResponse:
    """Align two fetched sequences and return the alignment result."""
    record_a = await _fetch_record(request, accession=accession_a, database=database)
    if accession_b:
        record_b = await _fetch_record(
            request, accession=accession_b, database=database
        )
    else:
        record_b = record_a

    return alignment_response(
        record_a,
        record_b,
        mode=mode,
        match_score=match_score,
        mismatch_score=mismatch_score,
        open_gap_score=open_gap_score,
        extend_gap_score=extend_gap_score,
    )


async def _fetch_record(
    request: Request, *, accession: str, database: str | None
) -> SequenceRecord:
    """Fetch *accession* from the named database (no error handling)."""
    client = _get_client(request, database)
    return await client.fetch(accession)
