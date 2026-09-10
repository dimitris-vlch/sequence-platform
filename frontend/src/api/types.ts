// TypeScript mirrors of the backend's Pydantic response schemas
// (`backend/src/sequence_platform/api/schemas.py`). Field names, optionality,
// and nesting must match that file exactly; change both together.
//
// Optionality notes, taken from the schemas themselves (not from a generic
// sense of what a sequence API "usually" returns):
// - `SearchHit.length` is `int | None` (ENA hits carry no length).
// - `SequenceStatisticsResponse.gc_content` is `float | None` (undefined for
//   sequences with no unambiguous bases).
// - `ComparisonResponse.hamming_distance` / `percent_identity` are
//   `int | None` / `float | None` (both null when the lengths differ).

/** Response body for `GET /api/health`. */
export interface HealthResponse {
  ok: boolean;
  service: string;
  version: string;
  time: string;
  databases: string[];
}

/** One entry in the `GET /api/databases` listing. */
export interface DatabaseInfo {
  name: string;
  available: boolean;
}

/** Response body for `GET /api/databases`. */
export interface DatabaseListResponse {
  databases: DatabaseInfo[];
}

/** One search result card. */
export interface SearchHit {
  accession: string;
  title: string;
  length: number | null;
  source_database: string;
  metadata: Record<string, unknown>;
}

/** Response body for `GET /api/databases/{name}/search`. */
export interface SearchResponse {
  query: string;
  results: SearchHit[];
}

/** A complete sequence record from `GET /api/databases/{name}/sequences/{accession}`. */
export interface SequenceRecordOut {
  accession: string;
  sequence: string;
  seq_type: string;
  length: number;
  title: string;
  description: string;
  source_database: string;
  metadata: Record<string, unknown>;
}

/** Response body for `GET /api/sequences/{accession}/statistics`. */
export interface SequenceStatisticsResponse {
  accession: string;
  seq_type: string;
  length: number;
  gc_content: number | null;
  base_composition: Record<string, number>;
  ambiguous_count: number;
  ambiguous_percentage: number;
  n_run_count: number;
  longest_n_run: number;
}

/** Response body for `GET /api/sequences/{accession}/quality`. */
export interface QualityReportResponse {
  accession: string;
  passed: boolean;
  issues: string[];
  min_length: number;
  max_ambiguous_fraction: number;
  max_n_run: number;
}

/** Response body for `GET /api/compare` (Stage 5). */
export interface ComparisonResponse {
  accession_a: string;
  accession_b: string;
  length_a: number;
  length_b: number;
  hamming_distance: number | null;
  percent_identity: number | null;
  levenshtein_distance: number;
  normalized_edit_similarity: number;
  jaccard_kmer_similarity: number;
  k: number;
}

/** Response body for `GET /api/align` (Stage 6). */
export interface AlignmentResponse {
  accession_a: string;
  accession_b: string;
  mode: string;
  score: number;
  aligned_a: string;
  aligned_b: string;
  start_a: number;
  end_a: number;
  start_b: number;
  end_b: number;
  match_score: number;
  mismatch_score: number;
  open_gap_score: number;
  extend_gap_score: number;
}

/** Query parameters for `GET /api/compare` (`k` is bounded 1-12 by the API). */
export interface CompareParams {
  accessionA: string;
  accessionB?: string;
  database?: string;
  k?: number;
}

/** Alignment modes accepted by `GET /api/align`. */
export type AlignmentMode = "global" | "local";

/** Query parameters for `GET /api/align`; scores default server-side. */
export interface AlignParams {
  accessionA: string;
  accessionB?: string;
  database?: string;
  mode?: AlignmentMode;
  match_score?: number;
  mismatch_score?: number;
  open_gap_score?: number;
  extend_gap_score?: number;
}

/** Threshold overrides for `GET /api/sequences/{accession}/quality`. */
export interface QualityThresholds {
  min_length?: number;
  max_ambiguous_fraction?: number;
  max_n_run?: number;
}
