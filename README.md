# Sequence Platform

A scientific web application for searching public nucleotide sequence
databases (NCBI, ENA), retrieving sequences and metadata, and performing
deterministic analysis: statistics, composition, similarity, distance,
alignment, quality control, visualization, and export.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19 + TypeScript + Vite |
| Backend | Python 3.12+ · FastAPI · Biopython · httpx |
| Testing | pytest · mypy · ruff · vitest |

## Architecture

```
React SPA (frontend/)
   │  /api (proxied to :8000 in dev)
   ▼
FastAPI application (backend/src/sequence_platform)
   ├── api/       HTTP layer: routes + Pydantic schemas (glue only)
   ├── database/  SequenceDatabase clients: NCBI (Stage 3), ENA (Stage 7)
   └── analysis/  pure, deterministic functions (Biopython only)
         ├── core           sequence model + utilities (Stage 2)
         ├── composition    GC content, nucleotide composition (Stage 4)
         ├── statistics     length, composition stats, orf checks (Stage 4)
         ├── similarity     identity, pairwise comparison (Stage 5)
         ├── distance       distance metrics (Stage 5)
         ├── alignment      pairwise alignment (Stage 6)
         └── quality_control  QC metrics (Stage 4)
```

**Layering rules** (enforced by review):

- `analysis/` imports only Biopython and the standard library. No network,
  no database module imports, no side effects.
- `database/` is the only layer that talks to external services. Clients
  implement one shared `SequenceDatabase` interface, return normalized
  records, and retain raw provider payloads for provenance.
- `api/` converts between HTTP/Pydantic and the other layers. It never
  implements biology or HTTP protocol details.
- The analysis layer must work with the same inputs regardless of which
  database a sequence came from.

## Scientific conventions (permanent project decisions)

- **GC content:** `GC% = (G + C) / (A + T + G + C) × 100`. Ambiguous
  nucleotides (N, R, Y, S, W, K, M, B, D, H, V) are excluded from the
  denominator and reported separately. This convention is fixed; any
  alternative is a separate, explicitly named function/option.

## Repository layout

```
sequence-platform/
├── .github/workflows/ci.yml   # backend (ruff + mypy + pytest) and frontend CI
├── backend/                   # FastAPI application (see backend/README.md)
├── frontend/                  # React application (see frontend/README.md)
└── docs/                      # architecture notes and stage decisions
```

Test fixtures are committed inside `backend/tests/conftest.py`, which is the
single source of the shared reference sequences.

## Getting started

Prerequisites: Python ≥ 3.12, Node ≥ 22.

```bash
# Backend (terminal 1)
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn sequence_platform.main:app --reload
# → http://127.0.0.1:8000  (health: GET /api/health)

# Frontend (terminal 2)
cd frontend
npm install
npm run dev
# → http://127.0.0.1:5173  (Vite proxies /api to :8000)
```

Optional: `cd backend && cp .env.example .env` and fill in `NCBI_EMAIL` /
`NCBI_API_KEY` (both optional; the key only raises the NCBI rate limit).

## Verification commands

| Check | Where | Command |
| --- | --- | --- |
| Backend lint | `backend/` | `ruff check .` |
| Backend types | `backend/` | `mypy` |
| Backend tests | `backend/` | `pytest` |
| Frontend types | `frontend/` | `npm run typecheck` |
| Frontend tests | `frontend/` | `npm test` |
| Frontend build | `frontend/` | `npm run build` |

## Development stages

| Stage | Deliverable |
| --- | --- |
| 1 | Project skeleton (this release) |
| 2 | Sequence data model and core utilities (Stage 2) |
| 3 | NCBI integration (Stage 3) |
| 4 | Sequence statistics and quality control (Stage 4) |
| 5 | Pairwise comparison and similarity (Stage 5) |
| 6 | Sequence alignment (Stage 6) |
| 7 | ENA integration (Stage 7) |
| 8 | Web interface and visualization (Stage 8) |
| 9 | Export and provenance (Stage 9) |
| 10 | Integration testing and production hardening (Stage 10) |

## Out of scope

Microservices, Kubernetes, authentication/authorization, cloud
infrastructure, and background workers are explicitly out of scope unless
explicitly requested.
