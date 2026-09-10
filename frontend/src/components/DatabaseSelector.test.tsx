import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DATABASES_RESPONSE, apiError, installFetchMock } from "../test/apiMock";
import { DatabaseSelector } from "./DatabaseSelector";

describe("DatabaseSelector", () => {
  it("lists providers and disables the ones with no client", async () => {
    installFetchMock({
      "GET /api/databases": {
        body: {
          databases: [
            { name: "ncbi", available: true },
            { name: "ena", available: false },
          ],
        },
      },
    });
    render(<DatabaseSelector value="ncbi" onChange={() => {}} />);
    expect(await screen.findByTestId("database-select")).toHaveValue("ncbi");
    expect(screen.getByRole("option", { name: "ncbi" })).toBeEnabled();
    expect(
      screen.getByRole("option", { name: "ena (unavailable)" }),
    ).toBeDisabled();
  });

  it("reports the selected provider through onChange", async () => {
    installFetchMock({ "GET /api/databases": { body: DATABASES_RESPONSE } });
    const onChange = vi.fn();
    render(<DatabaseSelector value="ncbi" onChange={onChange} />);
    await userEvent.selectOptions(
      await screen.findByTestId("database-select"),
      "ena",
    );
    expect(onChange).toHaveBeenCalledWith("ena");
  });

  it("warns when the selected provider is unavailable", async () => {
    installFetchMock({
      "GET /api/databases": {
        body: { databases: [{ name: "ncbi", available: false }] },
      },
    });
    render(<DatabaseSelector value="ncbi" onChange={() => {}} />);
    expect(await screen.findByTestId("database-select-unavailable")).toHaveTextContent(
      "ncbi",
    );
  });

  it("surfaces a failure to load the provider list", async () => {
    installFetchMock({ "GET /api/databases": apiError(503, "upstream down") });
    render(<DatabaseSelector value="ncbi" onChange={() => {}} />);
    expect(await screen.findByTestId("database-select-error")).toHaveTextContent(
      "upstream down",
    );
  });
});
