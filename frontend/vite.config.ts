import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

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
});
