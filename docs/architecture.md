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
  responses into the neutral domain model (the `models/` package).
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

### Stage 3 (NCBI client, typed errors, database routes)

- **Domain-model package**: §1's reference to a "`data/` package" was stale;
  the neutral domain model is the `models/` package (`SequenceRecord`,
  `SeqType`). §1 corrected.
- **`SequenceDatabase` interface** (`database/base.py`): abstract base with a
  `name` class attribute and three async methods — `fetch(accession) ->
  SequenceRecord`, `search(query, *, max_results=20) -> list[SequenceSummary]`,
  and `close()` (default no-op). `SequenceSummary` (accession, title, length,
  source_database, metadata) is a database-layer type defined alongside the
  interface; analysis consumes `SequenceRecord` only.
- **NCBI client** (`database/ncbi/client.py::NCBISequenceDatabase`,
  `name="ncbi"`): built on `httpx.AsyncClient` only (per §1). `Bio.Entrez` is
  *not* used for I/O; Biopython is used solely for the FASTA payload (Stage 2
  parser). Every request carries NCBI's `tool`/`email` parameters (plus
  `api_key` when configured).
  - Fetch flow: `esearch` (`count == 0` → `AccessionNotFoundError`) →
    `esummary` (optional metadata; raw JSON preserved in
    `metadata["ncbi_esummary"]`) → `efetch` (`rettype=fasta`,
    `retmode=text`) → `parse_fasta(..., infer_seq_type=True)`; exactly one
    parsed record is accepted. The client stamps `source_database="ncbi"`
    (the Stage 2 parser contract).
  - Retries (§2): 5xx / timeouts / network errors → up to `max_retries` (3)
    with exponential backoff (base 1 s, cap 30 s) × jitter (0.5–1.5) →
    `UpstreamUnavailableError` when exhausted; 429 → retried with
    `min(Retry-After, backoff_cap)` (the cap bounds a hostile header) →
    `RateLimitedError` when exhausted. Other 4xx (including NCBI's
    "unknown accession" 400) are *not* retried and map to
    `UpstreamUnavailableError`: after the esearch gate, a 400 means the
    server rejected a request we had already confirmed valid.
  - Seq-type inference for provider FASTA: sequence contains `U` → RNA, else
    DNA (IUPAC ambiguity codes contain neither U nor T; a record with both
    fails both alphabets → 422).
  - Constructor parameters: `email`, `api_key`, `db` (default `nucleotide`),
    `timeout` (30 s), `max_retries` (3), `backoff_base`/`backoff_cap`, and an
    optional `transport` for tests (satisfies §2's mock-transport rule without
    a new dependency; `respx` is not added to `pyproject.toml`).
- **Exceptions** (`database/exceptions.py`): a typed, HTTP-agnostic hierarchy
  — `DatabaseError`, `AccessionNotFoundError`, `UnknownDatabaseError`,
  `MalformedPayloadError`, `RateLimitedError` (carries `retry_after`),
  `UpstreamUnavailableError`. The API layer maps them: 404 / 404 / 422 / 429
  (+ `Retry-After` header) / 503, any other `DatabaseError` → 502; handlers
  are registered in `create_app()`, so routes never hand-map statuses.
- **`parse_fasta`** (`database/ncbi/fasta.py`): one new keyword-only argument
  `infer_seq_type: bool = False`; default behaviour is unchanged for existing
  callers (pinned in `tests/database/test_fasta.py`), the NCBI client uses it
  for mixed-alphabet provider FASTA.
- **Registry** (`database/registry.py`): extended with lazy `get_database(name)`
  (reads `Settings` at call time) and `registered_names()`; `ena` remains
  advertised-but-unregistered until Stage 7 and resolves to 404.
- **Routes** (`api/routes/databases.py`, schemas in `api/schemas.py`):
  `GET /api/databases` (advertised names + `available` flag),
  `GET /api/databases/{name}/sequences/{accession}`,
  `GET /api/databases/{name}/search?query&max_results` (1–100).
- **App lifecycle** (`main.py`): `create_app(databases=...)` accepts an
  injected client map (used by tests with a mocked transport); otherwise a
  lifespan builds one client per registered database at startup and closes them
  at shutdown (one connection pool per provider, not per request).
- **Tests**: canned NCBI fixtures (synthetic accessions, no real data) in
  `tests/conftest.py` served via `httpx.MockTransport`; route tests via
  `ASGITransport`. No committed test performs a real external request (§2).
