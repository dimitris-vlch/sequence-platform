"""External sequence database clients.

Each client (NCBI in Stage 3, ENA in Stage 7, ...) implements the same
``SequenceDatabase`` interface so the analysis layer never depends on a
particular archive. Clients are implemented here; no client code exists
yet in Stage 1.
"""
