"""Sequence comparison route (Stage 5) — ``GET /api/compare``.

Fetches two sequences from the selected database (or a single accession to
compare a record against itself) and returns the Stage 5 ``ComparisonReport``
— Hamming distance, percent identity, Levenshtein distance, normalised edit
similarity, and k-mer Jaccard similarity. The analysis itself lives in the
pure ``analysis`` package; this route only wires HTTP to it.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ...analysis.similarity import compare
from ...database.base import SequenceDatabase
from ...database.exceptions import UnknownDatabaseError
from ...models import SequenceRecord
from ..schemas import ComparisonResponse

router = APIRouter(prefix="/compare", tags=["compare"])


def _get_client(request: Request, name: str | None) -> SequenceDatabase:
    """Look up the long-lived client for *name* in app state.

    An empty/omitted name defaults to the NCBI client.

    Raises:
        UnknownDatabaseError: no client is registered under *name*; the
            API layer maps it to a 404.
    """
    key = "ncbi" if not name else name
    databases: dict[str, SequenceDatabase] = getattr(
        request.app.state, "databases", {}
    )
    client = databases.get(key)
    if client is None:
        raise UnknownDatabaseError(key)
    return client


@router.get("", response_model=ComparisonResponse)
async def compare_sequences(
    request: Request,
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
    k: int = Query(default=4, ge=1, le=12, description="k-mer size for Jaccard similarity"),
) -> ComparisonResponse:
    """Compare two fetched sequences and return all Stage 5 metrics."""
    record_a = await _fetch_record(request, accession=accession_a, database=database)
    if accession_b:
        record_b = await _fetch_record(request, accession=accession_b, database=database)
    else:
        record_b = record_a

    report = compare(record_a, record_b, k=k)
    return ComparisonResponse(
        accession_a=record_a.accession,
        accession_b=record_b.accession,
        length_a=report.length_a,
        length_b=report.length_b,
        hamming_distance=report.hamming_distance,
        percent_identity=report.percent_identity,
        levenshtein_distance=report.levenshtein_distance,
        normalized_edit_similarity=report.normalized_edit_similarity,
        jaccard_kmer_similarity=report.jaccard_kmer_similarity,
        k=k,
    )


async def _fetch_record(
    request: Request, *, accession: str, database: str | None
) -> SequenceRecord:
    """Fetch *accession* from the named database (no error handling)."""
    client = _get_client(request, database)
    return await client.fetch(accession)