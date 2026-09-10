# Sequence Platform - Backend

FastAPI backend for the Sequence Platform. It exposes the sequence
databases and analysis layer over a JSON API at `/api`.

## Layout

```
backend/
├── pyproject.toml              # dependencies + ruff/pytest/mypy config
├── .env.example                # documented environment template
├── src/sequence_platform/
│   ├── main.py                 # FastAPI app factory (routes under /api)
│   ├── config.py               # pydantic-settings (NCBI_EMAIL, NCBI_API_KEY)
│   ├── api/                    # thin HTTP layer: routes + Pydantic schemas
│   ├── database/               # SequenceDatabase clients (NCBI, ENA, ...)
│   └── analysis/               # pure, deterministic analysis modules
└── tests/                      # pytest suite (unit, api, database, integration)
```

Layering rules (enforced by review):

- `analysis/` imports only Biopython and the standard library. No network,
  no database module imports, no side effects.
- `database/` is the only layer that talks to external services. Clients
  implement the same `SequenceDatabase` interface and return normalized
  records; raw provider payloads are retained for provenance.
- `api/` is the glue: it converts between HTTP/Pydantic and the other
  layers. It never implements biology or HTTP protocol details.

## Project decisions

- **GC content convention (permanent):**
  `GC% = (G + C) / (A + T + G + C) * 100`. Ambiguous nucleotides (N, R, Y,
  S, W, K, M, B, D, H, V) are excluded from the denominator and reported
  separately. This convention is not changed silently; any alternative is
  a separate, explicitly named function/option.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Development

```bash
uvicorn sequence_platform.main:app --reload
# API base: http://127.0.0.1:8000  (health: GET /api/health)
```

Optional: `cp .env.example .env` and fill in `NCBI_EMAIL` / `NCBI_API_KEY`.

## Checks

```bash
ruff check .          # lint (default rules, 88 columns)
mypy                  # gradual type checking
pytest                # tests (no real network access)
```
