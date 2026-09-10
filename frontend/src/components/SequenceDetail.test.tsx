import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  QUALITY_RESPONSE,
  SEQUENCE_RECORD_RESPONSE,
  STATISTICS_RESPONSE,
  apiError,
  installFetchMock,
} from "../test/apiMock";
import { SequenceDetail } from "./SequenceDetail";

const RECORD_ROUTE = {
  "GET /api/databases/ncbi/sequences/NM_000001.1": {
    body: SEQUENCE_RECORD_RESPONSE,
  },
};
const STATS_ROUTE = {
  "GET /api/sequences/NM_000001.1/statistics": { body: STATISTICS_RESPONSE },
};
const QUALITY_ROUTE = {
  "GET /api/sequences/NM_000001.1/quality": { body: QUALITY_RESPONSE },
};
const DETAIL_ROUTES = { ...RECORD_ROUTE, ...STATS_ROUTE, ...QUALITY_ROUTE };

describe("SequenceDetail", () => {
  it("renders the sequence, its statistics, and its quality report", async () => {
    installFetchMock(DETAIL_ROUTES);
    render(<SequenceDetail database="ncbi" accession="NM_000001.1" />);

    expect(await screen.findByTestId("sequence-text")).toHaveTextContent(
      "ACGTACGTACGT",
    );
    expect(screen.getByTestId("statistics-length")).toHaveTextContent("12");
    expect(screen.getByTestId("statistics-gc")).toHaveTextContent("50%");
    expect(screen.getByText("A: 25%")).toBeInTheDocument();
    expect(screen.getByTestId("quality-status")).toHaveTextContent("Failed");
    expect(screen.getByTestId("quality-issues")).toHaveTextContent(
      "below the minimum 100",
    );
  });

  it("shows a single error when one of the three requests fails", async () => {
    installFetchMock({
      ...DETAIL_ROUTES,
      "GET /api/sequences/NM_000001.1/quality": apiError(404, "no such record"),
    });
    render(<SequenceDetail database="ncbi" accession="NM_000001.1" />);
    expect(await screen.findByTestId("detail-error")).toHaveTextContent(
      "no such record",
    );
  });

  it("renders a null GC content as an em dash, never a number", async () => {
    installFetchMock({
      ...DETAIL_ROUTES,
      "GET /api/sequences/NM_000001.1/statistics": {
        body: {
          ...STATISTICS_RESPONSE,
          gc_content: null,
          base_composition: { ambiguous: 100.0 },
        },
      },
    });
    render(<SequenceDetail database="ncbi" accession="NM_000001.1" />);
    expect(await screen.findByTestId("statistics-gc")).toHaveTextContent("—");
  });

  it("charts the base composition with the backend's numbers in the legend", async () => {
    installFetchMock(DETAIL_ROUTES);
    render(<SequenceDetail database="ncbi" accession="NM_000001.1" />);

    const chart = await screen.findByTestId("composition-chart");
    // recharts draws the donut as SVG paths inside the fixed-size chart.
    expect(chart.querySelectorAll("svg")).toHaveLength(1);
    expect(chart.querySelectorAll("path").length).toBeGreaterThan(0);
    // The legend keeps every category and its percentage as readable text.
    expect(screen.getByText("A: 25%")).toBeInTheDocument();
    expect(screen.getByText("ambiguous: 0%")).toBeInTheDocument();
  });

  it("charts the quality metrics against their thresholds", async () => {
    installFetchMock(DETAIL_ROUTES);
    render(<SequenceDetail database="ncbi" accession="NM_000001.1" />);

    expect(await screen.findByTestId("quality-chart")).toBeInTheDocument();
    const rows = screen.getByTestId("quality-rows");
    // Measured values come from the statistics response, thresholds from QC.
    expect(rows).toHaveTextContent("Length: 12 bp / threshold 100 bp (min)");
    expect(rows).toHaveTextContent("Ambiguous: 0% / threshold 10% (max)");
    expect(rows).toHaveTextContent("Longest N-run: 0 bases / threshold 10 bases");
    expect(rows).toHaveTextContent("12% of threshold");
  });

  it("offers FASTA and JSON export downloads for the loaded record", async () => {
    installFetchMock(DETAIL_ROUTES);
    render(<SequenceDetail database="ncbi" accession="NM_000001.1" />);
    await screen.findByTestId("sequence-text");
    expect(screen.getByTestId("export-fasta")).toHaveAttribute(
      "href",
      "/api/export/sequence/NM_000001.1/fasta?database=ncbi",
    );
    expect(screen.getByTestId("export-json")).toHaveAttribute(
      "href",
      "/api/export/sequence/NM_000001.1/json?database=ncbi",
    );
  });
});
