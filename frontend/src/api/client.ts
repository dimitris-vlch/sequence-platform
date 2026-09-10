// Typed wrappers around the backend JSON API. Every function maps 1:1 onto a
// FastAPI route; the response types live in ./types and mirror
// `backend/src/sequence_platform/api/schemas.py`.
//
// Errors: `fetchWithHttpError` turns any non-2xx response into an Error whose
// message is the backend's `{"detail": ...}` string, so components can render
// it directly.

import type {
  AlignParams,
  AlignmentResponse,
  CompareParams,
  ComparisonResponse,
  DatabaseListResponse,
  HealthResponse,
  QualityReportResponse,
  QualityThresholds,
  SearchResponse,
  SequenceRecordOut,
  SequenceStatisticsResponse,
} from "./types";

export type {
  AlignParams,
  AlignmentExportResponse,
  AlignmentMode,
  AlignmentResponse,
  CompareParams,
  ComparisonExportResponse,
  ComparisonResponse,
  DatabaseInfo,
  DatabaseListResponse,
  ExportProvenance,
  ExportSource,
  HealthResponse,
  QualityReportResponse,
  QualityThresholds,
  SearchHit,
  SearchResponse,
  SequenceExportResponse,
  SequenceRecordOut,
  SequenceStatisticsResponse,
} from "./types";

/**
 * Origin of the deployed backend API, or `""` when it is not configured.
 *
 * A trailing slash (easy to paste along with a copied URL) is ignored: an
 * origin never ends in one, and `https://host//api/health` is a different
 * path to the backend than `/api/health`.
 */
const apiOrigin = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

/**
 * Base path for every backend route.
 *
 * Empty `VITE_API_URL` — the default, and what local development and the test
 * suite run with — keeps the relative `/api` that the Vite dev server proxies
 * to the FastAPI dev server (see `vite.config.ts`). A production build sets
 * `VITE_API_URL` to the deployed backend's origin, so the same routes are
 * requested from `<origin>/api/...`: a static build has no dev proxy, and the
 * backend's `CORS_ORIGINS` must therefore list this site's origin.
 */
export const API_BASE_URL = `${apiOrigin}/api`;

export function httpErrorDetail(status: number, body: string): string {
  if (body === "") {
    return `HTTP ${status}`;
  }
  try {
    const parsed = JSON.parse(body) as { detail?: string };
    if (parsed.detail !== undefined) {
      return parsed.detail;
    }
  } catch {
    // Not JSON - fall back to the raw body.
  }
  return body.length > 120 ? `${body.slice(0, 120)}…` : body;
}

/** Normalise an unknown thrown value into a displayable message. */
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function fetchWithHttpError(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(httpErrorDetail(response.status, body));
  }
  return response;
}

/** Append defined query parameters to `path` (undefined values are omitted). */
function withQuery(
  path: string,
  params: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query === "" ? path : `${path}?${query}`;
}

/** Query the backend health endpoint. */
export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetchWithHttpError(`${API_BASE_URL}/health`);
  return (await response.json()) as HealthResponse;
}

/** List every archive the platform supports, with an `available` flag. */
export async function fetchDatabases(): Promise<DatabaseListResponse> {
  const response = await fetchWithHttpError(`${API_BASE_URL}/databases`);
  return (await response.json()) as DatabaseListResponse;
}

/** Fetch one complete sequence record. */
export async function fetchSequence(
  database: string,
  accession: string,
): Promise<SequenceRecordOut> {
  const response = await fetchWithHttpError(
    `${API_BASE_URL}/databases/${encodeURIComponent(database)}/sequences/${encodeURIComponent(accession)}`,
  );
  return (await response.json()) as SequenceRecordOut;
}

/** Free-text search; an empty `results` list is a normal outcome. */
export async function searchSequences(
  database: string,
  query: string,
  maxResults = 20,
): Promise<SearchResponse> {
  const response = await fetchWithHttpError(
    withQuery(`${API_BASE_URL}/databases/${encodeURIComponent(database)}/search`, {
      query,
      max_results: maxResults,
    }),
  );
  return (await response.json()) as SearchResponse;
}

/** Deterministic statistics for one record (`database` is required by the API). */
export async function fetchStatistics(
  accession: string,
  database: string,
): Promise<SequenceStatisticsResponse> {
  const response = await fetchWithHttpError(
    withQuery(`${API_BASE_URL}/sequences/${encodeURIComponent(accession)}/statistics`, {
      database,
    }),
  );
  return (await response.json()) as SequenceStatisticsResponse;
}

/** Threshold-based QC report; omitted thresholds use the server defaults. */
export async function fetchQuality(
  accession: string,
  database: string,
  thresholds: QualityThresholds = {},
): Promise<QualityReportResponse> {
  const response = await fetchWithHttpError(
    withQuery(`${API_BASE_URL}/sequences/${encodeURIComponent(accession)}/quality`, {
      database,
      min_length: thresholds.min_length,
      max_ambiguous_fraction: thresholds.max_ambiguous_fraction,
      max_n_run: thresholds.max_n_run,
    }),
  );
  return (await response.json()) as QualityReportResponse;
}

/** Compare two records (an empty `accessionB` compares A against itself). */
export async function compareSequences(
  params: CompareParams,
): Promise<ComparisonResponse> {
  const response = await fetchWithHttpError(
    withQuery(`${API_BASE_URL}/compare`, {
      accession_a: params.accessionA,
      accession_b: params.accessionB,
      database: params.database,
      k: params.k,
    }),
  );
  return (await response.json()) as ComparisonResponse;
}

/** Align two records (an empty `accessionB` aligns A against itself). */
export async function alignSequences(
  params: AlignParams,
): Promise<AlignmentResponse> {
  const response = await fetchWithHttpError(
    withQuery(`${API_BASE_URL}/align`, {
      accession_a: params.accessionA,
      accession_b: params.accessionB,
      database: params.database,
      mode: params.mode,
      match_score: params.match_score,
      mismatch_score: params.mismatch_score,
      open_gap_score: params.open_gap_score,
      extend_gap_score: params.extend_gap_score,
    }),
  );
  return (await response.json()) as AlignmentResponse;
}

// ---------------------------------------------------------------------------
// Export download URLs (Stage 9)
//
// The export routes are GET endpoints that set `Content-Disposition:
// attachment`, so a plain `<a href download>` triggers the download — no blob
// plumbing and no fetch wrapper. These builders keep the URL shape (which
// mirrors the read endpoint each export serialises) in one place.
// ---------------------------------------------------------------------------

/** URL that downloads one record as standard FASTA. */
export function sequenceFastaExportUrl(
  database: string,
  accession: string,
): string {
  return withQuery(
    `${API_BASE_URL}/export/sequence/${encodeURIComponent(accession)}/fasta`,
    { database },
  );
}

/** URL that downloads one record with statistics, QC report, and provenance. */
export function sequenceJsonExportUrl(
  database: string,
  accession: string,
): string {
  return withQuery(
    `${API_BASE_URL}/export/sequence/${encodeURIComponent(accession)}/json`,
    { database },
  );
}

/** URL that downloads a comparison as JSON. */
export function comparisonJsonExportUrl(params: CompareParams): string {
  return withQuery(`${API_BASE_URL}/export/compare/json`, {
    accession_a: params.accessionA,
    accession_b: params.accessionB,
    database: params.database,
    k: params.k,
  });
}

/** URL that downloads an alignment as JSON. */
export function alignmentJsonExportUrl(params: AlignParams): string {
  return withQuery(`${API_BASE_URL}/export/align/json`, alignmentQuery(params));
}

/** URL that downloads a pairwise alignment as human-readable text. */
export function alignmentTextExportUrl(params: AlignParams): string {
  return withQuery(`${API_BASE_URL}/export/align/text`, alignmentQuery(params));
}

/** Query parameters shared by both alignment export formats. */
function alignmentQuery(
  params: AlignParams,
): Record<string, string | number | undefined> {
  return {
    accession_a: params.accessionA,
    accession_b: params.accessionB,
    database: params.database,
    mode: params.mode,
    match_score: params.match_score,
    mismatch_score: params.mismatch_score,
    open_gap_score: params.open_gap_score,
    extend_gap_score: params.extend_gap_score,
  };
}
