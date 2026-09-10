"""Database-backed routes: listing, fetching, and searching sequences.

Routes are intentionally thin (§1 architecture rule): they look up the
long-lived client for the requested provider and call it, with no
try/except of their own. Every ``DatabaseError`` subclass raised by a
client propagates to the exception handlers registered in
``main.create_app``, which perform the actual status-code mapping.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ...database.base import SequenceDatabase
from ...database.exceptions import UnknownDatabaseError
from ...database.registry import SUPPORTED_DATABASES, registered_names
from ...models import SequenceRecord
from ..schemas import (
    DatabaseInfo,
    DatabaseListResponse,
    SearchHit,
    SearchResponse,
    SequenceRecordOut,
)

router = APIRouter()


def get_client(request: Request, name: str) -> SequenceDatabase:
    """Look up the long-lived client for ``name`` from app state.

    Public because the Stage 9 export routes (``routes/exports.py``) need the
    same lookup.

    Raises:
        UnknownDatabaseError: No client is registered under ``name``;
            mapped to 404 by the API layer.
    """
    databases: dict[str, SequenceDatabase] = getattr(request.app.state, "databases", {})
    client = databases.get(name)
    if client is None:
        available = ", ".join(registered_names())
        raise UnknownDatabaseError(
            f"No client registered for database {name!r}; registered: {available}"
        )
    return client


#: Metadata keys whose value is a raw provider payload kept for export
#: provenance. They are excluded from the compact record response (§6
#: Stage 9): the ENA FASTA text is as large as the sequence it contains and
#: roughly doubled ``/api/databases/{name}/sequences/{accession}``. A future
#: provider payload of the same kind is added here, so the filtering stays one
#: documented place rather than a per-provider special case.
_PROVENANCE_ONLY_METADATA_KEYS: frozenset[str] = frozenset(
    {"ena_fasta_raw", "ena_request_url"}
)


def compact_metadata(metadata: dict[str, object]) -> dict[str, object]:
    """Provider metadata minus the oversized provenance-only payloads.

    Only this HTTP-facing projection is filtered: the ``SequenceRecord`` keeps
    every key, and exports build their provenance from the record itself
    (``api/export.py::provenance``). Compact metadata — e.g. NCBI's parsed
    ``ncbi_esummary`` entry — passes through untouched.
    """
    return {
        key: value
        for key, value in metadata.items()
        if key not in _PROVENANCE_ONLY_METADATA_KEYS
    }


def to_record_out(record: SequenceRecord) -> SequenceRecordOut:
    """Convert a domain ``SequenceRecord`` into its API schema.

    Shared with the Stage 9 export routes, so a downloaded record and the
    ``/api/databases/{name}/sequences/{accession}`` response can never differ.
    The metadata projection drops the raw provider payloads (see
    ``compact_metadata``).
    """
    return SequenceRecordOut(
        accession=record.accession,
        sequence=record.sequence,
        seq_type=record.seq_type.value,
        length=record.length,
        title=record.title,
        description=record.description,
        source_database=record.source_database,
        metadata=compact_metadata(record.metadata),
    )


@router.get("/databases", response_model=DatabaseListResponse)
def list_databases(request: Request) -> DatabaseListResponse:
    """List every archive the platform is designed to support.

    Every entry in ``SUPPORTED_DATABASES`` is listed, including archives
    with no implemented client yet (``available: false``); this is a
    normal, non-error response.
    """
    databases: dict[str, SequenceDatabase] = getattr(request.app.state, "databases", {})
    return DatabaseListResponse(
        databases=[
            DatabaseInfo(name=name, available=name in databases)
            for name in SUPPORTED_DATABASES
        ]
    )


@router.get("/databases/{name}/sequences/{accession}", response_model=SequenceRecordOut)
async def fetch_sequence(
    request: Request, name: str, accession: str
) -> SequenceRecordOut:
    """Fetch one complete sequence record from database ``name``."""
    client = get_client(request, name)
    record = await client.fetch(accession)
    return to_record_out(record)


@router.get("/databases/{name}/search", response_model=SearchResponse)
async def search_database(
    request: Request,
    name: str,
    query: str,
    max_results: int = Query(default=20, ge=1, le=100),
) -> SearchResponse:
    """Run a free-text search against database ``name``.

    An empty result list is a normal, non-error response.
    """
    client = get_client(request, name)
    hits = await client.search(query, max_results=max_results)
    return SearchResponse(
        query=query,
        results=[
            SearchHit(
                accession=hit.accession,
                title=hit.title,
                length=hit.length,
                source_database=hit.source_database,
                metadata=hit.metadata,
            )
            for hit in hits
        ],
    )
