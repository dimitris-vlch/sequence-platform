import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The frontend talks to the backend API at /api. In development Vite
// proxies /api to the local FastAPI dev server, so no CORS issues and no
// build-time URL configuration are needed.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  // Component tests run in jsdom with Testing Library's matchers loaded from
  // `src/test/setup.ts`. `globals: true` gives Testing Library its global
  // `afterEach` hook so it auto-unmounts between tests.
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
