import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Unmount rendered trees and restore stubbed globals (e.g. `fetch`) between
// tests, so no test inherits another's DOM or network stub.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
