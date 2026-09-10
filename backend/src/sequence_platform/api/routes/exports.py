"""Export routes (Stage 9): FASTA, JSON, and pairwise-alignment text.

Every route serialises a result the platform already computes — through the
same schema builders as the corresponding read endpoint
(``routes/analysis.py``, ``routes/comparisons.py``, ``routes/alignment.py``),
so an export can never drift from the API response it mirrors — and returns
it with a ``Content-Disposition: attachment`` header, so one link downloads
it.

Dedicated ``/api/export/...`` routes rather than a ``?format=`` parameter on
the existing endpoints: no existing route varies its response shape by query
parameter, each route here keeps one static ``response_model`` (so the
generated OpenAPI stays accurate), and no route body branches on a format
flag (§1 thin-API rule). Route names echo the endpoint they serialise
(``/api/compare`` → ``/api/export/compare/json``). See §6 Stage 9.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from ...analysis import quality_control
from ...models import SequenceRecord
from ..export import (
    alignment_text,
    content_disposition,
    provenance,
    safe_filename,
)
from ..schemas import (
    AlignmentExportResponse,
    AlignmentResponse,
    ComparisonExportResponse,
    SequenceExportResponse,
)
from .alignment import alignment_response
from .analysis import quality_response, statistics_response
from .comparisons import comparison_response
from .databases import get_client, to_record_out

router = APIRouter(prefix="/export", tags=["export"])


async def _fetch_record(
    request: Request, *, accession: str, database: str
) -> SequenceRecord:
    """Fetch one record through the registered client (no error handling)."""
    client = get_client(request, database)
    return await client.fetch(accession)


async def _fetch_pair(
    request: Request, *, accession_a: str, accession_b: str, database: str
) -> tuple[SequenceRecord, SequenceRecord]:
    """Fetch A and B, or A twice when B is empty (as ``/compare`` does)."""
    record_a = await _fetch_record(request, accession=accession_a, database=database)
    if not accession_b:
        return record_a, record_a
    record_b = await _fetch_record(request, accession=accession_b, database=database)
    return record_a, record_b


@router.get("/sequence/{accession}/fasta")
async def export_sequence_fasta(
    request: Request,
    accession: str,
    database: str = Query(..., description="Provider name, e.g. 'ncbi'"),
) -> Response:
    """Download one record as standard FASTA (header + sequence only).

    FASTA has no place for statistics or a QC report, so this route fetches
    the record and nothing else — one provider request, not three.
    """
    record = await _fetch_record(request, accession=accession, database=database)
    return Response(
        content=record.to_fasta(),
        media_type="text/x-fasta",
        headers={
            "Content-Disposition": content_disposition(
                safe_filename(record.accession, ".fasta")
            )
        },
    )


@router.get("/sequence/{accession}/json", response_model=SequenceExportResponse)
async def export_sequence_json(
    request: Request,
    response: Response,
    accession: str,
    database: str = Query(..., description="Provider name, e.g. 'ncbi'"),
) -> SequenceExportResponse:
    """Download one record with its statistics, QC report, and provenance.

    The QC thresholds are the same defaults the
    ``/api/sequences/{accession}/quality`` route uses, and they are echoed
    inside the exported document, so the download is self-describing.
    """
    record = await _fetch_record(request, accession=accession, database=database)
    response.headers["Content-Disposition"] = content_disposition(
        safe_filename(record.accession, ".json")
    )
    return SequenceExportResponse(
        provenance=provenance([record]),
        record=to_record_out(record),
        statistics=statistics_response(record),
        quality=quality_response(
            record,
            min_length=quality_control.DEFAULT_MIN_LENGTH,
            max_ambiguous_fraction=quality_control.DEFAULT_MAX_AMBIGUOUS_FRACTION,
            max_n_run=quality_control.DEFAULT_MAX_N_RUN,
        ),
    )


async def _alignment_result(
    request: Request,
    *,
    accession_a: str,
    accession_b: str,
    database: str | None,
    mode: str,
    match_score: float,
    mismatch_score: float,
    open_gap_score: float,
    extend_gap_score: float,
) -> tuple[list[SequenceRecord], AlignmentResponse]:
    """Fetch both records and build the Stage 6 result (no error handling)."""
    records = await _fetch_pair(
        request,
        accession_a=accession_a,
        accession_b=accession_b,
        database=database or "ncbi",
    )
    alignment = alignment_response(
        *records,
        mode=mode,
        match_score=match_score,
        mismatch_score=mismatch_score,
        open_gap_score=open_gap_score,
        extend_gap_score=extend_gap_score,
    )
    return list(records), alignment


@router.get("/compare/json", response_model=ComparisonExportResponse)
async def export_comparison_json(
    request: Request,
    response: Response,
    accession_a: str = Query(
        min_length=1, description="Accession of the first sequence"
    ),
    accession_b: str = Query(
        default="",
        description="Accession of the second sequence; empty compares A against itself",
    ),
    database: str | None = Query(
        default=None, description="Database name to fetch from (default ncbi)"
    ),
    k: int = Query(
        default=4, ge=1, le=12, description="k-mer size for Jaccard similarity"
    ),
) -> ComparisonExportResponse:
    """Download a Stage 5 comparison (metrics + parameters) as JSON.

    The parameters mirror ``/api/compare`` exactly, including the
    ``database``-optional, default-to-NCBI behaviour.
    """
    record_a, record_b = await _fetch_pair(
        request,
        accession_a=accession_a,
        accession_b=accession_b,
        database=database or "ncbi",
    )
    response.headers["Content-Disposition"] = content_disposition(
        safe_filename(f"{record_a.accession}-vs-{record_b.accession}", ".json")
    )
    return ComparisonExportResponse(
        provenance=provenance([record_a, record_b], parameters={"k": k}),
        comparison=comparison_response(record_a, record_b, k=k),
    )


@router.get("/align/json", response_model=AlignmentExportResponse)
async def export_alignment_json(
    request: Request,
    response: Response,
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
        description="Alignment mode: 'global' or 'local'",
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
) -> AlignmentExportResponse:
    """Download a Stage 6 alignment (result + parameters) as JSON."""
    records, alignment = await _alignment_result(
        request,
        accession_a=accession_a,
        accession_b=accession_b,
        database=database,
        mode=mode,
        match_score=match_score,
        mismatch_score=mismatch_score,
        open_gap_score=open_gap_score,
        extend_gap_score=extend_gap_score,
    )
    response.headers["Content-Disposition"] = content_disposition(
        safe_filename(f"{alignment.accession_a}-vs-{alignment.accession_b}", ".json")
    )
    return AlignmentExportResponse(
        provenance=provenance(
            records,
            parameters={
                "mode": mode,
                "match_score": match_score,
                "mismatch_score": mismatch_score,
                "open_gap_score": open_gap_score,
                "extend_gap_score": extend_gap_score,
            },
        ),
        alignment=alignment,
    )


@router.get("/align/text")
async def export_alignment_text(
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
        description="Alignment mode: 'global' or 'local'",
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
) -> Response:
    """Download the pairwise alignment as text: both rows + the match line.

    The full aligned strings are written, untruncated — the UI truncates for
    display, an export does not.
    """
    _, alignment = await _alignment_result(
        request,
        accession_a=accession_a,
        accession_b=accession_b,
        database=database,
        mode=mode,
        match_score=match_score,
        mismatch_score=mismatch_score,
        open_gap_score=open_gap_score,
        extend_gap_score=extend_gap_score,
    )
    return Response(
        content=alignment_text(alignment),
        media_type="text/plain",
        headers={
            "Content-Disposition": content_disposition(
                safe_filename(
                    f"{alignment.accession_a}-vs-{alignment.accession_b}"
                    f"-{alignment.mode}",
                    ".txt",
                )
            )
        },
    )
