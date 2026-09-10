// Test helper: stub global `fetch` so component tests exercise the real
// `src/api/client.ts` code path without any network access. Every response is
// canned JSON built from the backend's own test fixtures' shapes.

import { vi } from "vitest";

export interface MockResponse {
  /** HTTP status; defaults to 200. */
  status?: number;
  /** JSON body; omit for an empty body. */
  body?: unknown;
}

/** Either a fixed response or a function of the request URL. */
export type MockRoute = MockResponse | ((url: URL) => MockResponse);

/**
 * Replace `globalThis.fetch` with a stub that routes by
 * `"<METHOD> <pathname>"` (query strings are ignored for matching, but the
 * parsed URL is passed to function routes so they can assert on it).
 *
 * Unmatched requests throw, so a test that calls an unexpected endpoint fails
 * loudly instead of silently returning an empty body.
 */
export function installFetchMock(
  routes: Record<string, MockRoute>,
): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const raw =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const url = new URL(raw, "http://localhost");
      const method = (init?.method ?? "GET").toUpperCase();
      const route = routes[`${method} ${url.pathname}`];
      if (route === undefined) {
        throw new Error(`Unexpected fetch: ${method} ${url.pathname}${url.search}`);
      }
      const result = typeof route === "function" ? route(url) : route;
      return jsonResponse(result.status ?? 200, result.body);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/**
 * Minimal `Response` double. `fetchWithHttpError` and the wrappers only use
 * `ok`, `status`, `text()`, and `json()`, so this avoids depending on a global
 * `Response` being present in the jsdom test environment.
 */
function jsonResponse(status: number, body: unknown): Response {
  const text = body === undefined ? "" : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => JSON.parse(text) as unknown,
  } as unknown as Response;
}

/** A backend error response (`{"detail": ...}`), as the API layer emits it. */
export function apiError(status: number, detail: string): MockResponse {
  return { status, body: { detail } };
}

// ---------------------------------------------------------------------------
// Canned payloads, shaped like real backend responses (12 bp ACGTACGTACGT).
// ---------------------------------------------------------------------------

export const DATABASES_RESPONSE = {
  databases: [
    { name: "ncbi", available: true },
    { name: "ena", available: true },
  ],
};

export const SEQUENCE_RECORD_RESPONSE = {
  accession: "NM_000001.1",
  sequence: "ACGTACGTACGT",
  seq_type: "dna",
  length: 12,
  title: "NM_000001.1 Homo sapiens test gene (TEST), mRNA",
  description: "Homo sapiens test gene (TEST), mRNA",
  source_database: "ncbi",
  metadata: {},
};

export const STATISTICS_RESPONSE = {
  accession: "NM_000001.1",
  seq_type: "dna",
  length: 12,
  gc_content: 50.0,
  base_composition: {
    A: 25.0,
    C: 25.0,
    G: 25.0,
    T: 25.0,
    ambiguous: 0.0,
  },
  ambiguous_count: 0,
  ambiguous_percentage: 0.0,
  n_run_count: 0,
  longest_n_run: 0,
};

export const QUALITY_RESPONSE = {
  accession: "NM_000001.1",
  passed: false,
  issues: ["length 12 is below the minimum 100"],
  min_length: 100,
  max_ambiguous_fraction: 0.1,
  max_n_run: 10,
};

export const SEARCH_RESPONSE = {
  query: "test",
  results: [
    {
      accession: "NM_000001.1",
      title: "Homo sapiens test gene (TEST), mRNA",
      length: 12,
      source_database: "ncbi",
      metadata: {},
    },
    {
      accession: "AB000001.1",
      title: "synthetic ENA test record",
      length: null,
      source_database: "ena",
      metadata: {},
    },
  ],
};

export const COMPARISON_RESPONSE = {
  accession_a: "NM_000001.1",
  accession_b: "NM_000001.1",
  length_a: 12,
  length_b: 12,
  hamming_distance: 0,
  percent_identity: 100.0,
  levenshtein_distance: 0,
  normalized_edit_similarity: 100.0,
  jaccard_kmer_similarity: 100.0,
  k: 4,
};

export const ALIGNMENT_RESPONSE = {
  accession_a: "NM_000001.1",
  accession_b: "NM_000001.1",
  mode: "global",
  score: 12.0,
  aligned_a: "ACGTACGTACGT",
  aligned_b: "ACGTACGTACGT",
  start_a: 0,
  end_a: 12,
  start_b: 0,
  end_b: 12,
  match_score: 1.0,
  mismatch_score: -1.0,
  open_gap_score: -2.0,
  extend_gap_score: -0.5,
};

//: A synthetic alignment containing all three column kinds: 6 matches, 1
//: mismatch, 1 gap (backend aligned strings use `-` for gaps and carry no
//: CIGAR, so the UI derives the column kinds from the two strings).
export const ALIGNMENT_WITH_GAPS_RESPONSE = {
  accession_a: "NM_000001.1",
  accession_b: "NM_000002.1",
  mode: "global",
  score: 3.0,
  aligned_a: "ACGTACGT",
  aligned_b: "ACGAAC-T",
  start_a: 0,
  end_a: 8,
  start_b: 0,
  end_b: 8,
  match_score: 1.0,
  mismatch_score: -1.0,
  open_gap_score: -2.0,
  extend_gap_score: -0.5,
};

/** The full happy-path route table shared by component and App tests. */
export const HAPPY_ROUTES: Record<string, MockRoute> = {
  "GET /api/health": {
    body: {
      ok: true,
      service: "sequence-platform",
      version: "0.1.0",
      time: "2026-01-01T00:00:00+00:00",
      databases: ["ncbi", "ena"],
    },
  },
  "GET /api/databases": { body: DATABASES_RESPONSE },
  "GET /api/databases/ncbi/sequences/NM_000001.1": {
    body: SEQUENCE_RECORD_RESPONSE,
  },
  "GET /api/databases/ncbi/search": { body: SEARCH_RESPONSE },
  "GET /api/sequences/NM_000001.1/statistics": { body: STATISTICS_RESPONSE },
  "GET /api/sequences/NM_000001.1/quality": { body: QUALITY_RESPONSE },
  "GET /api/compare": { body: COMPARISON_RESPONSE },
  "GET /api/align": { body: ALIGNMENT_RESPONSE },
};
