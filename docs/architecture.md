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

### Stage 5 (pairwise distance & similarity, compare route)

- **`analysis/distance`** (`analysis/distance/base.py`): pure, deterministic
  pairwise distance metrics. `hamming_distance(a, b)` (equal-length only;
  raises `ValueError` on unequal lengths — never truncates or pads),
  `percent_identity` (`100 * matches / length`, rounded to 2 dp; two empty
  sequences → `100.0`), and `levenshtein_distance` (classic unit-cost edit
  distance via a full O(n·m) DP table; works on unequal lengths). All three
  upper-case both inputs once (reusing the Stage 4 `_normalised` helper) so
  comparison is case-insensitive; ambiguity characters are treated as ordinary
  characters (byte-for-byte equality — no IUPAC overlap).
- **`analysis/similarity`** (`analysis/similarity/base.py`): pure pairwise
  similarity built on the distance metrics. `normalized_edit_similarity`
  (`100 * (1 - lev / max(len_a, len_b))`, clamped to `[0, 100]`, 2 dp; two
  empty sequences → `100.0`), `jaccard_kmer_similarity(a, b, *, k=4)` (Jaccard
  index over the k-mer sets as a percentage, 2 dp; both empty → `100.0`, one
  empty → `0.0`; raises `ValueError` if `k < 1` or a non-empty sequence is
  shorter than `k`), and the aggregating `compare(a, b, *, k=4) ->
  ComparisonReport`. `ComparisonReport` carries `length_a`/`length_b`,
  `hamming_distance` and `percent_identity` (both `None` when the sequences
  differ in length), `levenshtein_distance`, `normalized_edit_similarity`, and
  `jaccard_kmer_similarity`.
- **`GET /api/compare`** (`api/routes/comparisons.py`, `ComparisonResponse` in
  `api/schemas.py`): `accession_a` (required), `accession_b` (optional — empty
  compares A against itself), `database` (default `ncbi`), and `k` (1–12,
  default 4). Fetches both records via the selected client (Stage 3 registry
  lookup; `UnknownDatabaseError` → 404) and returns the `ComparisonReport`
  plus the accessions and the `k` used. The analysis itself is pure; the route
  only wires HTTP to it.
- **Tests**: known-answer tests in `tests/analysis/test_distance.py` and
  `tests/analysis/test_similarity.py` (hand-computed reference values,
  including unequal-length and empty-sequence edge cases); route tests in
  `tests/api/test_comparisons.py` via `ASGITransport` with a mocked client
  (no real external request, §2).

## Stage 6 — Pairwise Alignment

- **Scope**: `analysis/alignment` wraps Biopython `Bio.Align.PairwiseAligner`
  (already a dependency since Stage 2) behind two pure functions,
  `global_alignment` and `local_alignment`, plus a plain-dataclass
  `AlignmentResult` (score, gapped strings, and the six coordinate ints).
  No hand-rolled DP; the aligner is configured per call with the four
  scoring parameters, all keyword-only with defaults
  (`match_score=1.0`, `mismatch_score=-1.0`, `open_gap_score=-2.0`,
  `extend_gap_score=-0.5`).
- **Input handling**: both functions accept `SequenceLike` (str or
  `SequenceRecord`), upper-case via the shared `_normalised` helper, and
  raise `ValueError` on empty input. Tied optimal alignments (Biopython
  returns them in internal order) are resolved deterministically by taking
  `alignments[0]`.
- **Route**: `GET /api/align` in `api/routes/alignment.py` mirrors the
  Stage 5 comparisons pattern — `_get_client` → `_fetch_record` × 2 →
  dispatch on `mode` → `AlignmentResponse` (Pydantic, in `schemas.py`).
  Query params: `accession_a` (required), `accession_b` (optional, defaults
  to self), `database` (default `"ncbi"`), `mode` (`"global"`|`"local"`,
  default `"global"`), and the four score params (optional, same defaults).
  The response echoes the accessions, mode, score, gapped strings,
  coordinates, and the scoring parameters used.
- **Tests**: known-answer tests in `tests/analysis/test_alignment.py`
  (hand-computed scores for identical, mismatch, unequal-length, and
  local-subregion cases; empty-input and case-insensitivity edge cases);
  route tests in `tests/api/test_alignment.py` via `ASGITransport` with a
  mocked client (no real external request, §2).

### Stage 7 (ENA client, registry wiring)

- **ENA client** (`database/ena/client.py::ENASequenceDatabase`,
  `name="ena"`): the second real provider, built on `httpx.AsyncClient` only
  (per §1) and mirroring `NCBISequenceDatabase` structurally — same retry
  policy, same exception mapping, same provenance stamping. It has no
  `email`/`api_key` parameters: the ENA browser API requires no courtesy
  parameter.
  - Endpoints (fixed in Stage 7; never probed live — §2):
    `GET /fasta/{accession}` returns the record directly as plain FASTA text
    (no JSON envelope), and
    `GET /search?query&result=sequence&format=json&limit` returns a JSON
    array of hit objects carrying at least `accession` and `description`.
    Unlike NCBI's esearch there is no count field to gate on: an empty result
    is HTTP 200 with `[]`, which is a normal, non-error outcome.
  - Fetch flow: one `GET /fasta/{accession}` →
    `parse_fasta(..., infer_seq_type=True)`; exactly one parsed record is
    accepted and `source_database="ena"` is stamped (the Stage 2/3 provenance
    pattern). The parsed FASTA is the source of truth for sequence content,
    so no second metadata call is made and fetch stays a single request.
  - Retries (§2): 5xx / timeouts / network errors → up to `max_retries` (3)
    with exponential backoff (base 1 s, cap 30 s) × jitter (0.5–1.5) →
    `UpstreamUnavailableError` when exhausted; 429 → retried with
    `min(Retry-After, backoff_cap)` → `RateLimitedError` when exhausted; any
    other 4xx is *not* retried and maps immediately to
    `UpstreamUnavailableError`. HTTP 404 is unambiguous for ENA (unlike
    NCBI's quirk of answering unknown accessions with HTTP 400) and maps
    straight to `AccessionNotFoundError`, with no retry.
  - `search` maps each hit to `SequenceSummary(accession,
    title=<description>, length=None, source_database="ena", metadata=<raw
    hit>)`: ENA's hit objects carry no length, and fetching each hit's FASTA
    purely to fill one would defeat a lightweight search. The raw hit is
    preserved for provenance fidelity.
  - Constructor parameters: `base_url` (default
    `https://www.ebi.ac.uk/ena/browser/api`), `timeout` (30 s),
    `max_retries` (3), `backoff_base`/`backoff_cap`, and an optional
    `transport` for tests (satisfies §2's mock-transport rule without adding
    a dependency).
- **Registry** (`database/registry.py`): `ena` becomes the second entry in
  `_FACTORIES`, registered through the same `Callable[[Settings],
  SequenceDatabase]` factory-dict pattern. The ENA factory accepts `Settings`
  for type consistency and ignores it (nothing in `Settings` applies to ENA),
  and the client import stays deferred inside the factory body as it is for
  NCBI. `registered_names()` now yields `("ncbi", "ena")`, so
  `create_app`'s lifespan builds and closes an ENA client too; `config.py`
  is unchanged.
- **Routes** (`api/routes/databases.py`): no change needed — the routes
  resolve whatever is registered, so `GET /api/databases` now reports `ena`
  with `available: true` and the ENA fetch/search routes are live.
- **Tests**: synthetic ENA fixtures (a canned FASTA document and a canned
  search JSON array; no real data) in `tests/conftest.py`, served via
  `httpx.MockTransport`. Client tests in `tests/database/test_ena_client.py`
  cover the 404 → `AccessionNotFoundError` path, malformed/empty FASTA → 422,
  malformed search payloads, empty search, retry-then-succeed, exhausted 5xx
  and network errors → `UpstreamUnavailableError`, non-429 4xx not retried,
  and 429 → `RateLimitedError`. Route tests in `tests/api/test_databases.py`
  inject both mocked clients and drive the ENA routes via `ASGITransport`. No
  committed test performs a real external request (§2).
- **Flagged, not resolved unilaterally**: a 200 response with an empty body
  (zero parsed records) maps to `MalformedPayloadError`, because Stage 7
  fixes HTTP 404 as *the* ENA not-found signal and "exactly one record" as
  the acceptance rule; if a real ENA deployment instead answered some
  missing accessions with an empty 200, that mapping would need revisiting.
  Likewise, ENA search fields beyond `accession`/`description` are treated as
  optional (`None`/`""`) and never invented.

### Stage 8 (first React components)

- **Scope**: the first real UI — `frontend/src/api/` (one typed wrapper per
  backend route) and four components in `frontend/src/components/`
  (`DatabaseSelector`, `SequenceSearch`, `SequenceDetail`, `ComparisonView`)
  wired together in `App.tsx`. The two panels use plain conditional
  rendering; no routing dependency was added (`react-router` is not in
  `package.json`), and no new dependency of any kind — `fetch` directly, with
  `vitest` + `@testing-library/react` as already installed since Stage 1.
- **Type contract** (`frontend/src/api/types.ts`): one interface per Pydantic
  response model in `api/schemas.py`, field-for-field —
  `HealthResponse` (health route shape), `DatabaseInfo`/`DatabaseListResponse`,
  `SearchHit`/`SearchResponse` (`length: number | null`, since ENA hits carry
  none), `SequenceRecordOut`, `SequenceStatisticsResponse`
  (`gc_content: number | null`), `QualityReportResponse`, `ComparisonResponse`
  (`hamming_distance`/`percent_identity` nullable), `AlignmentResponse` — plus
  the query-parameter types that are not response schemas (`CompareParams`,
  `AlignParams`, `AlignmentMode`, `QualityThresholds`). `client.ts` re-exports
  them, so a component imports its wrapper and its type from one place.
- **API client** (`frontend/src/api/client.ts`): keeps the Stage 1
  `API_BASE_URL` / `httpErrorDetail` / `fetchWithHttpError` helpers (a non-2xx
  response becomes an `Error` carrying the backend's `{"detail": ...}`),
  adds `errorMessage` for unknown throws, and exposes `fetchHealth`,
  `fetchDatabases`, `fetchSequence`, `searchSequences`, `fetchStatistics`,
  `fetchQuality`, `compareSequences`, `alignSequences`. `fetchStatistics` and
  `fetchQuality` send the `database` parameter the API requires; undefined
  query parameters are omitted so the server defaults apply (`k=4`,
  `mode=global`, QC thresholds).
- **Components**: `DatabaseSelector` loads `GET /api/databases` and disables
  providers with `available: false` (they stay visible — the API advertises
  them deliberately); `SequenceSearch` queries
  `GET /api/databases/{name}/search` and lists the hits (a `null` length
  renders as “—”); `SequenceDetail` fetches the record, its statistics, and
  its QC report together behind one loading/error state; `ComparisonView`
  owns its own database selector plus the two accession inputs and renders the
  Stage 5 metrics from `GET /api/compare` (an empty accession B compares A
  with itself, as documented).
- **`App.tsx`**: header, the Stage 1 backend-status block (now using the
  shared `errorMessage` helper), a search/compare toggle, the shared database
  selector, and the panels. No biology and no status-code mapping in the
  frontend: the API layer owns the error vocabulary, the UI only displays the
  message it is given.
- **Alignment**: `alignSequences` is implemented and tested as part of the
  client layer (the endpoint must stay covered), but no alignment UI is built
  in Stage 8 — alignment visualisation is explicitly out of scope for this
  stage.
- **Tests**: `frontend/src/test/apiMock.ts` stubs global `fetch` by
  `"<METHOD> <pathname>"`, so component tests drive the real `client.ts` code
  path with canned JSON and no network; `src/test/setup.ts` unmounts trees and
  restores stubbed globals between tests; `vite.config.ts` gains a `test`
  block (jsdom environment, `setupFiles`, `globals`) so the Stage 1
  `setup.ts` is actually loaded — without it `vitest run` defaulted to the
  Node environment and Testing Library matchers were never registered. Tests
  are colocated as `src/**/*.test.tsx`; no test (and no component) contacts
  anything but the local `/api` proxy — never NCBI or ENA directly.

### Stage 8.5 (visualization layer)

- **Scope**: the visual layer Stage 8 deferred — a base-composition chart and a
  quality-metrics chart inside `SequenceDetail`, plus a new `AlignmentView`
  that is the first UI to call the Stage 6 `/api/align` endpoint. One new
  dependency: `recharts` (`^3.10.1`, React 19-compatible, TypeScript types
  bundled), used for both charts — the one charting library in the project.
  The alignment rendering deliberately does *not* use it: per-character
  match/mismatch/gap colouring is coloured `<span>`s, not a chart, and forcing
  character data into a chart library would fight its data model.
- **`AlignmentResponse` shape (verified against `schemas.py`, not assumed)**:
  `accession_a`, `accession_b`, `mode`, `score`, `aligned_a`, `aligned_b`,
  `start_a`/`end_a`/`start_b`/`end_b`, and the four scores. There is **no CIGAR
  string and no per-column data**; `analysis/alignment/base.py` builds the
  aligned strings with `str(best[0])`/`str(best[1])` and documents `-` as the
  gap character. `AlignmentView` therefore derives its per-column
  classification from the two gapped strings (gap vs match vs mismatch) and
  counts those columns itself — display arithmetic over returned strings, with
  no re-implementation of the alignment algorithm.
- **`AlignmentView`** (`components/AlignmentView.tsx`): mirrors
  `ComparisonView` exactly — own `DatabaseSelector`
  (`id="alignment-database-select"`), two accession inputs, one
  loading/error state, the same `errorMessage` helper, and an omitted (not
  empty) accession B so the API's "align A against itself" default applies. It
  adds `mode` (`global`/`local`) and the four scoring inputs, all passed
  through the existing `alignSequences()` wrapper — no new API function and no
  change to `api/types.ts`. Rendered: score, column count, match/mismatch/gap
  counts, aligned regions, the scoring used, and the two aligned rows with
  three CSS classes (`col-match`, `col-mismatch`, `col-gap`) plus a legend. At
  most 400 columns are rendered (one `<span>` each); beyond that the panel says
  how many columns were withheld rather than truncating silently.
- **Charts** (`SequenceDetail.tsx`, local components): base composition as a
  `PieChart` donut plus a legend carrying the exact percentages (the numbers
  stay readable text, the pie gives the shape at a glance); the QC report as a
  horizontal `BarChart` of "% of threshold" per check — length vs
  `min_length`, `ambiguous_percentage` vs `max_ambiguous_fraction × 100`,
  longest N-run vs `max_n_run` — with a reference line at 100 and the exact
  measured/threshold numbers listed beneath. Charts use fixed pixel sizes, not
  `ResponsiveContainer`: the panel is a fixed-width column, and fixed sizes
  render deterministically under jsdom. The pass/fail verdict is still the
  backend's (`passed` + `issues`); the frontend does not re-derive QC
  thresholds, and it does not recompute `base_composition`.
- **`App.tsx`**: the toggle becomes three panels — `type View = "search" |
  "compare" | "align"` — with the third nav button rendering `AlignmentView`;
  still plain conditional rendering, still no routing dependency.
- **Tests**: `AlignmentView.test.tsx` covers input → call → rendered alignment
  (including asserting the three colour classes, the derived 6/1/1
  match/mismatch/gap counts from a canned gapped fixture, `mode` forwarding,
  the 400-column cap, the API-error path, and the required-accession guard);
  `SequenceDetail.test.tsx` gains assertions that both charts render and that
  the composition legend and quality rows carry the backend's numbers. All
  network access stays stubbed via `test/apiMock.ts` (which gained
  `ALIGNMENT_WITH_GAPS_RESPONSE`) — no test touches a live backend, and the
  frontend still only ever calls `/api`.

### Stage 9 (export and provenance)

- **Export routes** (`api/routes/exports.py`): five GET endpoints, one per
  target/format — `/api/export/sequence/{accession}/fasta`,
  `/api/export/sequence/{accession}/json`, `/api/export/compare/json`,
  `/api/export/align/json`, `/api/export/align/text`. Dedicated routes rather
  than a `?format=` parameter on the existing endpoints: no existing route
  varies its response shape by query parameter, each route here keeps one
  static `response_model` (so the generated OpenAPI stays accurate), and no
  route body branches on a format flag (§1 thin-API rule). Names echo the
  endpoint each export serialises (`/api/compare` → `/api/export/compare/json`);
  `database` is required where the read endpoint requires it (`/statistics`,
  `/quality`) and optional-with-NCBI-default where `/compare` and `/align` are,
  so the inconsistency the Stage 7 audit flagged remains open rather than
  being silently changed. Every route returns
  `Content-Disposition: attachment` with a sanitised filename.
- **Shared builders instead of duplicated mapping**: `statistics_response` /
  `quality_response` (`routes/analysis.py`), `comparison_response`
  (`routes/comparisons.py`), `alignment_response` (`routes/alignment.py`) and
  `get_client` / `to_record_out` (`routes/databases.py`, renamed from private
  names) were extracted from the read routes, which now delegate to them.
  Behaviour is unchanged and the existing route tests pass untouched; an
  export can no longer drift from the endpoint it mirrors. The other route
  modules keep their own private `_get_client` copies (not refactored here).
- **Serialisation helpers** (`api/export.py`, FastAPI-free and unit-tested):
  `provenance()` builds the §4 block (UTC `generated_at`, application and
  version, one `ExportSource` per input record carrying accession, source
  database, length, sequence MD5 digest and the raw provider metadata, plus the
  analysis `parameters`); `sequence_md5()`, `safe_filename()` /
  `content_disposition()` (accessions are user input and end up in a response
  header, so everything outside `[A-Za-z0-9._-]` is replaced and an empty stem
  becomes `export`), and `match_line()` / `alignment_text()`.
- **Reused formatting, not reinvented**: FASTA comes from
  `SequenceRecord.to_fasta()`, the domain model's entry point into
  `database/ncbi/fasta.py` — the platform's single Biopython-backed FASTA
  writer since Stage 2 (a route test asserts the retrieved FASTA round-trips
  byte-for-byte). The alignment text match line is new code of necessity:
  `analysis/alignment` returns only the two gapped strings (the Biopython
  `Alignment` object is discarded), so Biopython's own `str(alignment)` display
  is unreachable from the API layer and re-running the aligner would compute
  rather than serialise. It emits `|` / `.` / space per column over the full
  untruncated strings with padded labels, plus a header line carrying mode,
  score and match/mismatch/gap counts — the same three-way classification the
  Stage 8.5 alignment view uses for colouring.
- **Formats**: a sequence exports as FASTA (header + sequence only — FASTA has
  no place for statistics, and fetching them would cost two extra provider
  calls) or as a self-contained JSON document (provenance + record +
  statistics + QC report, with the QC thresholds echoed); a comparison and an
  alignment export as JSON (`provenance` + the Stage 5/6 response schema); an
  alignment also exports as pairwise text. No GenBank/XML/CSV, and no batch
  export.
- **Part B — ENA provenance fix** (`database/ena/client.py`): `fetch` now
  retains the payload it always had in hand — `metadata["ena_fasta_raw"]` (the
  response text) and `metadata["ena_request_url"]` (the URL actually
  requested) — closing the asymmetry the Stage 7 audit flagged against NCBI's
  `metadata["ncbi_esummary"]`. Same return type, same exceptions, same
  normalized fields; the one existing test that pinned `metadata == {}`
  (`tests/database/test_ena_client.py::test_fetch_happy_path`) was updated to
  assert the new keys rather than the fix being avoided. Known trade-off: the
  raw text duplicates the sequence for long records, so
  `/sequences/{accession}` responses for ENA records now carry it as well.
- **Frontend**: `api/types.ts` gains `ExportSource`, `ExportProvenance`,
  `SequenceExportResponse`, `ComparisonExportResponse` and
  `AlignmentExportResponse`; `api/client.ts` gains five pure URL builders
  (`sequenceFastaExportUrl`, `sequenceJsonExportUrl`,
  `comparisonJsonExportUrl`, `alignmentJsonExportUrl`,
  `alignmentTextExportUrl`). Because the routes set `Content-Disposition`, the
  triggers are plain `<a download>` links — no blob plumbing and no new
  dependency. `SequenceDetail` (FASTA + JSON), `ComparisonView` (JSON) and
  `AlignmentView` (JSON + text, rebuilt from the response so a download
  reproduces what is on screen) render them only once a result exists.
- **Tests**: `tests/api/test_exports.py` covers all five routes end to end with
  injected mocked clients (FASTA round-trip for both providers; the JSON
  envelopes with their provenance, MD5 digests and raw metadata; the Part B
  assertion that an exported ENA record carries `ena_fasta_raw`; 404s for an
  unknown accession and an unknown database; parameter forwarding for compare
  and align) plus unit tests for the pure formatters. Frontend tests cover the
  URL builders and the rendered link hrefs. No test performs a real external
  request (§2).
- **Metadata filtering on the plain record response** (`routes/databases.py`):
  the ENA provenance payload (`metadata["ena_fasta_raw"]`, plus
  `ena_request_url`) stays on the domain `SequenceRecord`, but `to_record_out()`
  — the only HTTP-facing projection of a record — drops keys listed in one
  documented place, `_PROVENANCE_ONLY_METADATA_KEYS`, via `compact_metadata()`.
  The raw FASTA text duplicates the sequence and roughly doubled
  `/api/databases/{name}/sequences/{accession}` (measured: 197 B → 346 B for the
  12 bp fixture, 10 188 B → 20 290 B at 10 kb). The choice is a denylist rather
  than an allowlist or a size heuristic: it changes nothing except the keys we
  already know to be oversized (a future compact provider field still reaches
  the response, where an allowlist would silently drop it), and the response
  shape stays deterministic rather than depending on payload size. The filter
  is a property of that response shape, not of ENA — a future oversized
  provider payload is added to the same set. Compact metadata is untouched:
  NCBI's `ncbi_esummary` still appears in the record response (pinned by
  `test_fetch_sequence_happy_path`) and in export provenance
  (`test_export_sequence_json_carries_record_statistics_quality_provenance`).
  Exports keep the full payload in `provenance.sources[].metadata` (pinned by
  `test_export_sequence_json_ena_retains_the_raw_provider_payload`), so in the
  sequence JSON export the raw text now appears exactly once, in the provenance
  block, instead of also duplicating it in the `record` sub-object
  (also pinned). The frontend needs no change: no component reads `metadata`
  (`SequenceDetail` renders only named record fields).

### Stage 10 (integration testing and production hardening)

- **Integration test layer** (`backend/tests/integration/`): a genuinely new
  layer, not a relabelling of what existed. `tests/api/` exercises one endpoint
  per test against a freshly built app; these tests build the app **once** and
  drive a multi-step flow through it. `test_user_journeys.py` walks list
  databases → search → fetch → statistics → quality → compare → align → export
  for NCBI, repeats the journey for ENA, and pins the property no single-route
  test can observe: *the same app* answering both sides, with each export
  document compared field-for-field against the read endpoint that produced it
  (`export["record"] == record`, `export["statistics"] == statistics`,
  `export["quality"] == quality`, `alignment_export["alignment"] == alignment`,
  and the align/text rows against the `/api/align` response). One error-path
  test asserts an unknown accession/database maps to the same 404 JSON shape
  across all three route families. Honest accounting: this adds cross-route
  agreement and shared-app coverage, **not** new per-endpoint edge cases —
  those were already thorough per route (Stages 3–9). It did surface one thing
  the shared conftest handlers cannot express, though: a two-accession NCBI stub,
  so the journey also compares *unequal-length* records (Hamming/identity `null`,
  edit distance 2) instead of the same record with itself.
- **Frontend flow test** (`frontend/src/App.flows.test.tsx`): one comparison
  driven through the real `App` tree (panel tab → form → fetch → metrics →
  export link), beyond the per-component tests and `App.test.tsx`'s
  search→detail flow. No new dependency: no Playwright/Cypress exist in this
  project and none were added.
- **Error mapping (item 1)**: the six `database/exceptions.py` types were
  already mapped (404 / 404 / 422 / 429 + `Retry-After` / 503, any other
  `DatabaseError` → 502). The real gap was not a typed exception: `analysis/`
  signals caller-contract violations with a plain `ValueError`, `/api/compare`
  accepts `k` up to 12, and a record shorter than `k` therefore escaped the
  ASGI app unhandled — `GET /api/compare?accession_a=<10 bp>&k=11` produced
  `ValueError: sequence a (length 10) is shorter than k=11` out of the
  application (verified before the fix; a 500 in production). `main.py` now
  maps `ValueError` → 422 JSON, `SequenceValidationError` → 422 (a safety net:
  the clients already convert it to `MalformedPayloadError`), and registers an
  `Exception` → 500 handler that returns the platform's `{"detail": ...}` shape
  while logging the traceback server-side. pydantic's `ValidationError` is a
  `ValueError` subclass, so the `ValueError` handler re-raises it: a
  response-model bug stays a 500 and is never blamed on the caller. `analysis/`
  was not modified — the mapping belongs to the HTTP layer (§1).
- **CORS (item 2)**: verified already correct, no change. The allowlist holds
  the two Vite dev origins rather than a wildcard, and `allow_credentials=True`
  is paired only with explicit origins (`*` plus credentials is the invalid
  combination). **Flagged decision**: the deployment shape is undocumented — the
  SPA reaches `/api` through the Vite proxy and no production origin appears
  anywhere in the repository — so a configurable `CORS_ORIGINS` setting was not
  invented. If the SPA is ever served from another origin, the constant in
  `main.py` must become configuration.
- **Configuration (item 3)**: verified already correct, no change. There is no
  required configuration to fail fast on: `Settings` exposes two optional
  `str | None` fields with safe defaults, `.env.example` shows them empty, and
  the app starts with nothing set (`tests/test_config.py` pins that, and that
  empty values are accepted while unknown keys are ignored via
  `extra="ignore"`). Nothing can be malformed in a way that fails later: the
  fields are plain strings, so no coercion can fail. Two notes recorded rather
  than changed: values are read from `.env` relative to the working directory,
  which is why the documented `cd backend` first step matters, and an unfilled
  `.env` yields `""` rather than `None`, which the NCBI client drops anyway
  (`_common_params()` only includes `email` when it is truthy).
- **Logging (item 4)**: added, standard library only. `main.py` gained
  `configure_logging()` (called at import; `basicConfig`, so a host process's
  logging configuration always wins and repeated calls cannot stack handlers),
  one access line per request (method, path, status, duration — path only, never
  the query string), and a start-up line carrying the version. Both provider
  clients now log every retry decision (WARNING: 5xx/timeout with attempt count,
  429 with `Retry-After`), every exhausted or non-retried failure (ERROR), and
  ENA's normal 404 (INFO). The change is additive: no retry decision, return
  value, or exception type changed.
- **Health (item 5)**: verified already correct, no change. `/api/health` is a
  **liveness** probe (`ok`, `service`, `version`, `time`, advertised database
  names) and deliberately not a readiness probe: making it depend on NCBI/ENA
  reachability would make the endpoint exactly as reliable as the providers §2
  calls unreliable, and would require a live request to test. Provider trouble
  is already reported per request as a typed 404/429/503.
- **Dependency pinning (item 6)**: assessed, no pin changed (out of scope).
  Frontend: `package-lock.json` is committed and ranges are `^`/`~`, so installs
  are reproducible — but CI and the README run `npm install`, which can
  re-resolve; `npm ci` is the reproducible command. Backend: there is no lock
  file at all, only lower bounds (`biopython>=1.85`, `fastapi>=0.115`, ...), so a
  fresh `pip install -e ".[dev]"` may resolve different versions over time.
  **Flagged risk**: the backend build is not bit-reproducible; adding a lock or
  exact pins needs a dependency review, which this stage deliberately does not do.
- **README/docs accuracy (item 7)**: the Getting-started commands were executed
  as written (venv, `pip install -e ".[dev]"`, the documented
  `uvicorn sequence_platform.main:app`, `npm install` / `npm test` /
  `npm run build`), and the documented ports (backend 8000, Vite 5173) match
  `frontend/vite.config.ts`'s proxy target `http://127.0.0.1:8000`. The Stage 8
  ("Web interface and visualization") and Stage 9 ("Export and provenance")
  roadmap rows are present and accurate. One clear inaccuracy fixed: the
  repository-layout block listed a `data/` directory that does not exist (the
  shared fixtures live in `backend/tests/conftest.py`); `backend/README.md`'s
  layout line now also names the integration suite.
- **CI**: unchanged and still accurate. `pytest` runs with
  `testpaths = ["tests"]`, so `tests/integration/` is collected without a
  workflow edit.
