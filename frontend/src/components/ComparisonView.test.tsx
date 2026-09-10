import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  COMPARISON_RESPONSE,
  DATABASES_RESPONSE,
  apiError,
  installFetchMock,
} from "../test/apiMock";
import { ComparisonView } from "./ComparisonView";

const ROUTES = {
  "GET /api/databases": { body: DATABASES_RESPONSE },
  "GET /api/compare": { body: COMPARISON_RESPONSE },
};

/** URLs the stub was called with that target /api/compare. */
function compareCalls(fetchMock: ReturnType<typeof installFetchMock>): string[] {
  return fetchMock.mock.calls
    .map((call) => String(call[0]))
    .filter((url) => url.startsWith("/api/compare"));
}

describe("ComparisonView", () => {
  it("compares two accessions and renders the Stage 5 metrics", async () => {
    const fetchMock = installFetchMock(ROUTES);
    render(<ComparisonView />);
    await userEvent.type(screen.getByLabelText("Accession A"), "NM_000001.1");
    await userEvent.click(screen.getByRole("button", { name: "Compare" }));

    expect(await screen.findByTestId("compare-result")).toBeInTheDocument();
    expect(screen.getByTestId("compare-lengths")).toHaveTextContent("12");
    expect(screen.getByTestId("compare-hamming")).toHaveTextContent("0");
    expect(screen.getByTestId("compare-identity")).toHaveTextContent("100");
    expect(screen.getByText("Jaccard k-mer similarity (k=4)")).toBeInTheDocument();

    const url = compareCalls(fetchMock)[0] ?? "";
    expect(url).toContain("accession_a=NM_000001.1");
    expect(url).toContain("database=ncbi");
    expect(url).toContain("k=4");
    // An empty second accession is omitted, so the backend compares A to itself.
    expect(url).not.toContain("accession_b=");
  });

  it("renders nullable metrics as em dashes", async () => {
    installFetchMock({
      ...ROUTES,
      "GET /api/compare": {
        body: {
          ...COMPARISON_RESPONSE,
          hamming_distance: null,
          percent_identity: null,
          length_b: 7,
        },
      },
    });
    render(<ComparisonView />);
    await userEvent.type(screen.getByLabelText("Accession A"), "NM_000001.1");
    await userEvent.click(screen.getByRole("button", { name: "Compare" }));
    await screen.findByTestId("compare-result");
    expect(screen.getByTestId("compare-hamming")).toHaveTextContent("—");
    expect(screen.getByTestId("compare-identity")).toHaveTextContent("—");
  });

  it("requires the first accession before calling the API", async () => {
    const fetchMock = installFetchMock(ROUTES);
    render(<ComparisonView />);
    await userEvent.click(screen.getByRole("button", { name: "Compare" }));
    expect(await screen.findByTestId("compare-error")).toHaveTextContent(
      "Enter the first accession",
    );
    expect(compareCalls(fetchMock)).toHaveLength(0);
  });

  it("shows the backend error message", async () => {
    installFetchMock({
      ...ROUTES,
      "GET /api/compare": apiError(404, "unknown accession"),
    });
    render(<ComparisonView />);
    await userEvent.type(screen.getByLabelText("Accession A"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Compare" }));
    expect(await screen.findByTestId("compare-error")).toHaveTextContent(
      "unknown accession",
    );
  });

  it("offers a JSON export of the computed comparison", async () => {
    installFetchMock(ROUTES);
    render(<ComparisonView />);
    await userEvent.type(screen.getByLabelText("Accession A"), "NM_000001.1");
    await userEvent.click(screen.getByRole("button", { name: "Compare" }));
    expect(await screen.findByTestId("compare-export-json")).toHaveAttribute(
      "href",
      "/api/export/compare/json?accession_a=NM_000001.1&accession_b=NM_000001.1&database=ncbi&k=4",
    );
  });
});
