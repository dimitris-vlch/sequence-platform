"""Database client registry.

Database clients are added here (NCBI in Stage 3, ENA in Stage 7).
Stage 1 ships no clients yet; the registry only advertises which
databases the platform is designed to support.
"""

__all__ = ["SUPPORTED_DATABASES"]

# Databases planned for the first release, in display order.
SUPPORTED_DATABASES: tuple[str, ...] = ("ncbi", "ena")
