import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SEARCH_RESPONSE, apiError, installFetchMock } from "../test/apiMock";
import { SequenceSearch } from "./SequenceSearch";

const SEARCH_ROUTE = { "GET /api/databases/ncbi/search": { body: SEARCH_RESPONSE } };

describe("SequenceSearch", () => {
  it("submits a query and renders one row per hit", async () => {
    const fetchMock = installFetchMock(SEARCH_ROUTE);
    render(<SequenceSearch database="ncbi" onSelect={() => {}} />);
    await userEvent.type(screen.getByLabelText("Query"), "test");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(
      await screen.findByRole("button", { name: "NM_000001.1" }),
    ).toBeInTheDocument();
    expect(screen.getByText("synthetic ENA test record")).toBeInTheDocument();
    // The ENA hit has length null; it must render as an em dash, not "null".
    expect(screen.getAllByText("—")).toHaveLength(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("max_results=20");
  });

  it("treats an empty result list as a normal outcome", async () => {
    installFetchMock({
      "GET /api/databases/ncbi/search": {
        body: { query: "nothing", results: [] },
      },
    });
    render(<SequenceSearch database="ncbi" onSelect={() => {}} />);
    await userEvent.type(screen.getByLabelText("Query"), "nothing");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByTestId("search-empty")).toHaveTextContent(
      "No results",
    );
  });

  it("reports the clicked hit's accession", async () => {
    installFetchMock(SEARCH_ROUTE);
    const onSelect = vi.fn();
    render(<SequenceSearch database="ncbi" onSelect={onSelect} />);
    await userEvent.type(screen.getByLabelText("Query"), "test");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "AB000001.1" }),
    );
    expect(onSelect).toHaveBeenCalledWith("AB000001.1");
  });

  it("shows the backend error message", async () => {
    installFetchMock({
      "GET /api/databases/ncbi/search": apiError(503, "upstream down"),
    });
    render(<SequenceSearch database="ncbi" onSelect={() => {}} />);
    await userEvent.type(screen.getByLabelText("Query"), "test");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByTestId("search-error")).toHaveTextContent(
      "upstream down",
    );
  });

  it("requires a query before calling the API", async () => {
    const fetchMock = installFetchMock({});
    render(<SequenceSearch database="ncbi" onSelect={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByTestId("search-error")).toHaveTextContent(
      "Enter a search term",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
