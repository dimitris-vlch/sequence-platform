import { describe, expect, it } from "vitest";

// Lightweight placeholder suite so the test toolchain is verified in CI.
// Real component tests (rendering App with a mocked API client) arrive in
// Stage 8 alongside the first real UI.
describe("frontend test suite", () => {
  it("runs", () => {
    expect(1 + 1).toBe(2);
  });
});
