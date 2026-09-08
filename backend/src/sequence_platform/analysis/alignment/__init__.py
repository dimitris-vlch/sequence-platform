"""Pairwise sequence alignment (Stage 6).

Public API:
    AlignmentResult
    global_alignment
    local_alignment
"""

from .base import AlignmentResult, global_alignment, local_alignment

__all__ = ["AlignmentResult", "global_alignment", "local_alignment"]
