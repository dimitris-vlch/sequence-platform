"""Pydantic response schemas for the API layer.

These are pure serialization types: they mirror the database-layer
dataclasses (`SequenceRecord`, `SequenceSummary`) field-for-field but never
carry behaviour of their own. Routes build them explicitly from domain
objects rather than relying on ORM-style coercion, keeping the API layer
thin (§1 architecture rule).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DatabaseInfo(BaseModel):
    """One entry in the ``GET /api/databases`` listing."""

    name: str
    available: bool


class DatabaseListResponse(BaseModel):
    """Response body for ``GET /api/databases``."""

    databases: list[DatabaseInfo]


class SearchHit(BaseModel):
    """One search result card, mirroring ``SequenceSummary``."""

    accession: str
    title: str = ""
    length: int | None = None
    source_database: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Response body for ``GET /api/databases/{name}/search``."""

    query: str
    results: list[SearchHit]


class SequenceRecordOut(BaseModel):
    """A complete sequence record, mirroring ``SequenceRecord``."""

    accession: str
    sequence: str
    seq_type: str
    length: int
    title: str = ""
    description: str = ""
    source_database: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class ErrorBody(BaseModel):
    """Uniform error payload for every mapped ``DatabaseError``."""

    detail: str
