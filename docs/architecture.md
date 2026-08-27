# Architecture Notes

This document records binding architectural decisions for the Sequence
Platform. It is the reference for all stage work; changes here require a
conscious decision and a note in this file.

## 1. Layering

```
frontend/ (React + TypeScript SPA)
    │  fetch /api/*
    ▼
backend: api/          — FastAPI routes + Pydantic schemas (HTTP↔domain glue)
    │
    ├── database/      — external service clients (NCBI, ENA, future)
    └── analysis/      — pure deterministic functions (Biopython + stdlib only)
```

Rules:

- `analysis/` must import only Biopython, the Python standard library, and
  other `analysis/` modules. No network, no `database/` imports, no I/O, no
  global state. Every function must be testable in isolation.
- `database/` is the only layer allowed to use `httpx`. Each client
  implements the `SequenceDatabase` interface and converts provider
  responses into the neutral domain model (`data/` package).
- `api/` is thin: validation, status-code mapping, schema serialization.
  It orchestrates `database/` and `analysis/` but implements no biology.
- The analysis layer must be database-agnostic: the same function accepts a
  sequence whether it came from NCBI, ENA, or a local upload.

## 2. External-service policy

NCBI and ENA are treated as unreliable dependencies:

- Every client call sets an explicit timeout (default 30 s, configurable).
- All I/O is wrapped with retry + exponential backoff + jitter, for
  5xx, network errors, and 429 (NCBI `Retry-After` is honored).
- `database/` defines the platform's typed exception hierarchy; clients
  raise only those types. The `api/` layer maps them to HTTP status
  codes (404 unknown accession, 422 malformed payload, 429 rate limited,
  503 upstream down).
- Missing optional metadata never raises; it maps to `None` and is
  preserved (as `null` in exports) for provenance fidelity.
- Required metadata that the upstream did not provide must be marked
  unknown — the platform must never invent values.
- All tests mock the network (httpx transport / ASGI transport). No
  committed test performs a real external request.

## 3. Scientific conventions

- **GC content**: `GC% = (G + C) / (A + T + G + C) × 100`. Ambiguous
  nucleotides (IUPAC: N, R, Y, S, W, K, M, B, D, H, V) are excluded from
  the denominator and reported as a separate field.
- **Sequence identity / distance**: definitions are fixed in Stage 5 with
  documented, tested formulas; ambiguity handling is explicit in each
  function's contract.
- **Known-answer tests**: all scientific tests use small hand-computed
  reference values. Test data is deterministic and shared in
  `backend/tests/conftest.py`.
- **Alignment (Stage 6)**: default scoring (substitution matrix, gap
  penalties) is fixed and documented; parameters are explicit function
  arguments so callers can vary them without changing the algorithm.

## 4. Provenance

Every analysis result records: input accessions (+ source database),
input sequence lengths and MD5 digests, function name and version, full
parameter set, and UTC timestamp. The complete provenance chain is
exportable (Stage 9).

## 5. Deliberately out of scope

Microservices, Kubernetes, authentication/authorization, cloud
infrastructure, distributed processing, and background workers are out
of scope unless explicitly requested in a future stage.

## 6. Per-stage decisions

Stage decisions that were left open during planning are appended below as
they are made (Stage 2 onward).

### Stage 1 (skeleton)

- Python ≥ 3.12 (3.12 for local + CI matrix; both 3.12 and 3.13 supported).
- Frontend: React 19, TypeScript 5.x, Vite, vitest.
- Tooling: ruff (lint + format), mypy, pytest on the backend; vitest +
  Testing Library on the frontend.
- Frontend `src/components/` is a placeholder package (single import-free
  file); the first real components arrive in Stage 8.
- Backend ships an `api/` layer with a `/api/health` endpoint; the
  remaining endpoints appear as their stages land.
- `.env` support: optional `NCBI_EMAIL` / `NCBI_API_KEY`; both have safe
  defaults; `.env` itself is gitignored; `.env.example` is committed.
