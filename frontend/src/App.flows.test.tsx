// Stage 10: a user flow driven through the real App component tree, rather
// than one component in isolation the way the colocated component tests do.
// No new dependency — vitest + Testing Library + the existing fetch stub, the
// same setup every other frontend test already uses (no Playwright/Cypress in
// this project, and none added).

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import App from "./App";
import { HAPPY_ROUTES, installFetchMock } from "./test/apiMock";

describe("App comparison flow", () => {
  it("compares an accession from the Compare panel and offers the export", async () => {
    const fetchMock = installFetchMock(HAPPY_ROUTES);
    render(<App />);

    // The panel tab and the form's submit button share the accessible name
    // "Compare"; the tab renders first, so the submit is the last match.
    const compareButtons = await screen.findAllByRole("button", {
      name: "Compare",
    });
    await userEvent.click(compareButtons[0] ?? screen.getByRole("button"));
    await userEvent.type(screen.getByLabelText("Accession A"), "NM_000001.1");
    const submit = screen.getAllByRole("button", { name: "Compare" }).at(-1);
    if (submit === undefined) {
      throw new Error("no Compare submit button");
    }
    await userEvent.click(submit);

    expect(await screen.findByTestId("compare-identity")).toHaveTextContent("100");
    const compareUrl = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .find((url) => url.startsWith("/api/compare"));
    expect(compareUrl).toContain("database=ncbi");
    expect(await screen.findByTestId("compare-export-json")).toHaveAttribute(
      "href",
      "/api/export/compare/json?accession_a=NM_000001.1&accession_b=NM_000001.1&database=ncbi&k=4",
    );
  });
});
