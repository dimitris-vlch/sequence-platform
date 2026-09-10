import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  ALIGNMENT_RESPONSE,
  ALIGNMENT_WITH_GAPS_RESPONSE,
  DATABASES_RESPONSE,
  apiError,
  installFetchMock,
} from "../test/apiMock";
import { AlignmentView } from "./AlignmentView";

const ROUTES = {
  "GET /api/databases": { body: DATABASES_RESPONSE },
  // The real route echoes back the mode it used, so mirror that here: the
  // panel must show the response's mode, not the requested one.
  "GET /api/align": (url: URL) => ({
    body: {
      ...ALIGNMENT_WITH_GAPS_RESPONSE,
      mode: url.searchParams.get("mode") ?? "global",
    },
  }),
};

/** URLs the stub was called with that target /api/align. */
function alignCalls(fetchMock: ReturnType<typeof installFetchMock>): string[] {
  return fetchMock.mock.calls
    .map((call) => String(call[0]))
    .filter((url) => url.startsWith("/api/align"));
}

/** Number of coloured character spans rendered in alignment row `row`. */
function renderedColumns(container: HTMLElement, row: number): number {
  const rows = container.querySelectorAll(".alignment-row");
  return rows[row]?.querySelectorAll("span").length ?? 0;
}

describe("AlignmentView", () => {
  it("runs the full input → call → rendered alignment flow", async () => {
    const fetchMock = installFetchMock(ROUTES);
    const { container } = render(<AlignmentView />);

    await userEvent.type(screen.getByLabelText(/Accession A/), "NM_000001.1");
    await userEvent.type(
      screen.getByLabelText(/Accession B/),
      "NM_000002.1",
    );
    await userEvent.selectOptions(screen.getByLabelText("Mode"), "local");
    await userEvent.click(screen.getByRole("button", { name: "Align" }));

    expect(await screen.findByTestId("align-result")).toBeInTheDocument();
    expect(screen.getByTestId("align-score")).toHaveTextContent("3");
    expect(screen.getByTestId("align-mode-value")).toHaveTextContent("local");
    expect(screen.getByTestId("align-columns")).toHaveTextContent("8");
    // Derived from the two gapped strings: 6 matches, 1 mismatch, 1 gap.
    expect(screen.getByTestId("align-counts")).toHaveTextContent("6 / 1 / 1");

    // Each of the eight columns is coloured in both rows.
    expect(renderedColumns(container, 0)).toBe(8);
    expect(renderedColumns(container, 1)).toBe(8);
    // Scoped to the rows: the legend swatches reuse the same classes.
    const rowsContainer = screen.getByTestId("alignment-rows");
    expect(rowsContainer.querySelectorAll(".col-match")).toHaveLength(12);
    expect(rowsContainer.querySelectorAll(".col-mismatch")).toHaveLength(2);
    expect(rowsContainer.querySelectorAll(".col-gap")).toHaveLength(2);

    const url = alignCalls(fetchMock)[0] ?? "";
    expect(url).toContain("accession_a=NM_000001.1");
    expect(url).toContain("accession_b=NM_000002.1");
    expect(url).toContain("database=ncbi");
    expect(url).toContain("mode=local");
    expect(url).toContain("match_score=1");
  });

  it("caps the rendered columns instead of truncating silently", async () => {
    const longSequence = "A".repeat(500);
    installFetchMock({
      "GET /api/databases": { body: DATABASES_RESPONSE },
      "GET /api/align": {
        body: {
          ...ALIGNMENT_RESPONSE,
          aligned_a: longSequence,
          aligned_b: longSequence,
        },
      },
    });
    const { container } = render(<AlignmentView />);
    await userEvent.type(screen.getByLabelText(/Accession A/), "NM_000001.1");
    await userEvent.click(screen.getByRole("button", { name: "Align" }));

    expect(await screen.findByTestId("align-truncated")).toHaveTextContent(
      "Showing the first 400 of 500 columns",
    );
    expect(renderedColumns(container, 0)).toBe(400);
  });

  it("requires the first accession before calling the API", async () => {
    const fetchMock = installFetchMock(ROUTES);
    render(<AlignmentView />);
    await userEvent.click(screen.getByRole("button", { name: "Align" }));
    expect(await screen.findByTestId("align-error")).toHaveTextContent(
      "Enter the first accession",
    );
    expect(alignCalls(fetchMock)).toHaveLength(0);
  });

  it("shows the backend error message", async () => {
    installFetchMock({
      "GET /api/databases": { body: DATABASES_RESPONSE },
      "GET /api/align": apiError(404, "unknown accession"),
    });
    render(<AlignmentView />);
    await userEvent.type(screen.getByLabelText(/Accession A/), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Align" }));
    expect(await screen.findByTestId("align-error")).toHaveTextContent(
      "unknown accession",
    );
  });
});
