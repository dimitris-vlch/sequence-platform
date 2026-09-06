"""Pairwise sequence similarity (Stage 5).

Exposes the pairwise similarity metrics (edit-similarity, k-mer Jaccard, and
the aggregated :func:`compare`) from :mod:`.base`.
"""

from sequence_platform.analysis.similarity.base import (
    ComparisonReport,
    compare,
    jaccard_kmer_similarity,
    normalized_edit_similarity,
)

__all__ = [
    "ComparisonReport",
    "base",
    "compare",
    "jaccard_kmer_similarity",
    "normalized_edit_similarity",
]

