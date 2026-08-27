# Sequence Platform - Frontend

React 19 + TypeScript SPA (Vite). In Stage 1 it renders an application
shell with a live backend status indicator.

## Setup

```bash
npm install
npm run dev          # → http://127.0.0.1:5173
```

The Vite dev server proxies `/api/*` to the backend at
`http://127.0.0.1:8000` (see `vite.config.ts`). The backend must be
running for the status indicator to show "running".

## Scripts

| Script | Purpose |
| --- | --- |
| `npm run dev` | Dev server with the `/api` proxy |
| `npm run build` | Type check (`tsc -b`) + production build to `dist/` |
| `npm test` | vitest (one-shot; `npm test -- --watch` to watch) |
| `npm run typecheck` | `tsc -b` only |

## Layout

```
src/
├── api/client.ts       # typed API client (add endpoints per stage)
├── components/         # feature components (Stage 8+)
├── App.tsx             # application shell
├── main.tsx            # entry point
└── styles.css          # minimal global styles
```

## Tests

vitest + Testing Library (jsdom). Component tests live next to their
components (`App.test.ts` style) and mock `src/api/client.ts` rather than
hitting a real backend.
