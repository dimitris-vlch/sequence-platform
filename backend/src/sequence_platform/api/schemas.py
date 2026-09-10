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


class SequenceStatisticsResponse(BaseModel):
    """Response body for ``GET /api/sequences/{accession}/statistics``."""

    accession: str
    seq_type: str
    length: int
    gc_content: float | None
    base_composition: dict[str, float]
    ambiguous_count: int
    ambiguous_percentage: float
    n_run_count: int
    longest_n_run: int


class QualityReportResponse(BaseModel):
    """Response body for ``GET /api/sequences/{accession}/quality``."""

    accession: str
    passed: bool
    issues: list[str]
    min_length: int
    max_ambiguous_fraction: float
    max_n_run: int


class ComparisonResponse(BaseModel):
    """Response body for GET /api/compare (Stage 5)."""

    accession_a: str
    accession_b: str
    length_a: int
    length_b: int
    hamming_distance: int | None
    percent_identity: float | None
    levenshtein_distance: int
    normalized_edit_similarity: float
    jaccard_kmer_similarity: float
    k: int


class AlignmentResponse(BaseModel):
    """Response body for GET /api/align (Stage 6)."""

    accession_a: str
    accession_b: str
    mode: str
    score: float
    aligned_a: str
    aligned_b: str
    start_a: int
    end_a: int
    start_b: int
    end_b: int
    match_score: float
    mismatch_score: float
    open_gap_score: float
    extend_gap_score: float


class ExportSource(BaseModel):
    """Provenance for one input record of an export (§4).

    ``md5`` is the hex MD5 digest of the sequence exactly as the platform
    holds it (upper-case, no whitespace), and ``metadata`` is the raw
    provider payload the client retained (e.g. ``ncbi_esummary`` /
    ``ena_fasta_raw``), so an exported document can be traced back to what
    the archive actually returned.
    """

    accession: str
    source_database: str
    length: int
    md5: str
    metadata: dict[str, object] = Field(default_factory=dict)


class ExportProvenance(BaseModel):
    """The provenance block every JSON export carries (§4).

    ``generated_at`` is a UTC ISO-8601 timestamp; ``sources`` holds one entry
    per input record (two for a comparison or alignment); ``parameters``
    holds the analysis parameters the exported result was computed with.
    """

    generated_at: str
    application: str
    version: str
    sources: list[ExportSource]
    parameters: dict[str, object] = Field(default_factory=dict)


class SequenceExportResponse(BaseModel):
    """Response body for ``GET /api/export/sequence/{accession}/json``."""

    provenance: ExportProvenance
    record: SequenceRecordOut
    statistics: SequenceStatisticsResponse
    quality: QualityReportResponse


class ComparisonExportResponse(BaseModel):
    """Response body for ``GET /api/export/compare/json``."""

    provenance: ExportProvenance
    comparison: ComparisonResponse


class AlignmentExportResponse(BaseModel):
    """Response body for ``GET /api/export/align/json``."""

    provenance: ExportProvenance
    alignment: AlignmentResponse
