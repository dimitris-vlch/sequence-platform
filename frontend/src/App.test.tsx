import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import App from "./App";
import { HAPPY_ROUTES, apiError, installFetchMock } from "./test/apiMock";

describe("App", () => {
  it("reports backend health and lists the databases", async () => {
    installFetchMock(HAPPY_ROUTES);
    render(<App />);
    expect(await screen.findByTestId("backend-status")).toHaveTextContent(
      "sequence-platform v0.1.0 is running",
    );
    expect(await screen.findByTestId("database-select")).toHaveValue("ncbi");
    expect(screen.getByRole("option", { name: "ena" })).toBeInTheDocument();
  });

  it("keeps the startup hint when the backend is unreachable", async () => {
    installFetchMock({
      "GET /api/health": apiError(503, "connection refused"),
    });
    render(<App />);
    expect(await screen.findByTestId("backend-status")).toHaveTextContent(
      "Cannot reach the backend",
    );
  });

  it("runs the search → detail flow end to end", async () => {
    installFetchMock(HAPPY_ROUTES);
    render(<App />);
    await userEvent.type(screen.getByLabelText("Query"), "test");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "NM_000001.1" }),
    );
    expect(await screen.findByTestId("sequence-text")).toHaveTextContent(
      "ACGTACGTACGT",
    );
    expect(screen.getByTestId("quality-status")).toHaveTextContent("Failed");
  });

  it("switches to the comparison panel", async () => {
    installFetchMock(HAPPY_ROUTES);
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Compare" }));
    expect(screen.getByLabelText("Accession A")).toBeInTheDocument();
    expect(
      await screen.findByTestId("comparison-database-select"),
    ).toBeInTheDocument();
  });

  it("switches to the alignment panel", async () => {
    installFetchMock(HAPPY_ROUTES);
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Align" }));
    expect(screen.getByLabelText("Mode")).toBeInTheDocument();
    expect(
      await screen.findByTestId("alignment-database-select"),
    ).toBeInTheDocument();
  });
});
