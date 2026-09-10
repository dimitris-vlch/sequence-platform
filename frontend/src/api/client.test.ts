import { describe, expect, it } from "vitest";

import {
  ALIGNMENT_RESPONSE,
  COMPARISON_RESPONSE,
  DATABASES_RESPONSE,
  HAPPY_ROUTES,
  QUALITY_RESPONSE,
  SEARCH_RESPONSE,
  SEQUENCE_RECORD_RESPONSE,
  STATISTICS_RESPONSE,
  apiError,
  installFetchMock,
} from "../test/apiMock";
import {
  alignSequences,
  compareSequences,
  fetchDatabases,
  fetchQuality,
  fetchSequence,
  fetchStatistics,
  httpErrorDetail,
  searchSequences,
} from "./client";

/** Read the URL the stubbed fetch was called with, for call `index`. */
function calledUrl(fetchMock: ReturnType<typeof installFetchMock>, index = 0): string {
  return String(fetchMock.mock.calls[index]?.[0]);
}

describe("api client", () => {
  it("fetchDatabases parses the list from GET /api/databases", async () => {
    const fetchMock = installFetchMock(HAPPY_ROUTES);
    await expect(fetchDatabases()).resolves.toEqual(DATABASES_RESPONSE);
    expect(calledUrl(fetchMock)).toBe("/api/databases");
  });

  it("fetchSequence builds the accession path", async () => {
    const fetchMock = installFetchMock(HAPPY_ROUTES);
    await expect(fetchSequence("ncbi", "NM_000001.1")).resolves.toEqual(
      SEQUENCE_RECORD_RESPONSE,
    );
    expect(calledUrl(fetchMock)).toBe(
      "/api/databases/ncbi/sequences/NM_000001.1",
    );
  });

  it("searchSequences sends query and max_results", async () => {
    const fetchMock = installFetchMock(HAPPY_ROUTES);
    await expect(searchSequences("ncbi", "test", 5)).resolves.toEqual(
      SEARCH_RESPONSE,
    );
    const url = calledUrl(fetchMock);
    expect(url).toContain("/api/databases/ncbi/search");
    expect(url).toContain("query=test");
    expect(url).toContain("max_results=5");
  });

  it("fetchStatistics always sends the required database parameter", async () => {
    const fetchMock = installFetchMock(HAPPY_ROUTES);
    await expect(fetchStatistics("NM_000001.1", "ncbi")).resolves.toEqual(
      STATISTICS_RESPONSE,
    );
    expect(calledUrl(fetchMock)).toBe(
      "/api/sequences/NM_000001.1/statistics?database=ncbi",
    );
  });

  it("fetchQuality omits undefined thresholds so server defaults apply", async () => {
    const fetchMock = installFetchMock(HAPPY_ROUTES);
    await expect(fetchQuality("NM_000001.1", "ncbi")).resolves.toEqual(
      QUALITY_RESPONSE,
    );
    const url = calledUrl(fetchMock);
    expect(url).toContain("database=ncbi");
    expect(url).not.toContain("min_length");
    expect(url).not.toContain("max_n_run");
  });

  it("fetchQuality forwards explicit thresholds", async () => {
    const fetchMock = installFetchMock(HAPPY_ROUTES);
    await fetchQuality("NM_000001.1", "ncbi", { min_length: 5, max_n_run: 3 });
    const url = calledUrl(fetchMock);
    expect(url).toContain("min_length=5");
    expect(url).toContain("max_n_run=3");
  });

  it("compareSequences mirrors the GET /api/compare parameters", async () => {
    const fetchMock = installFetchMock(HAPPY_ROUTES);
    await expect(
      compareSequences({
        accessionA: "NM_000001.1",
        accessionB: "",
        database: "ncbi",
        k: 4,
      }),
    ).resolves.toEqual(COMPARISON_RESPONSE);
    const url = calledUrl(fetchMock);
    expect(url).toContain("/api/compare");
    expect(url).toContain("accession_a=NM_000001.1");
    expect(url).toContain("database=ncbi");
    expect(url).toContain("k=4");
  });

  it("alignSequences leaves mode and scores to the server defaults", async () => {
    const fetchMock = installFetchMock(HAPPY_ROUTES);
    await expect(alignSequences({ accessionA: "NM_000001.1" })).resolves.toEqual(
      ALIGNMENT_RESPONSE,
    );
    const url = calledUrl(fetchMock);
    expect(url).toContain("/api/align");
    expect(url).toContain("accession_a=NM_000001.1");
    expect(url).not.toContain("mode=");
    expect(url).not.toContain("open_gap_score=");
  });

  it("surfaces the backend's detail string when a request fails", async () => {
    installFetchMock({
      "GET /api/databases/ncbi/sequences/missing": apiError(404, "No record"),
    });
    await expect(fetchSequence("ncbi", "missing")).rejects.toThrow("No record");
  });

  it("falls back to the status code when the body carries no detail", () => {
    expect(httpErrorDetail(500, "")).toBe("HTTP 500");
    expect(httpErrorDetail(500, "not json")).toBe("not json");
  });
});
