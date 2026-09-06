"""Sequence distance metrics (Stage 5).

Pure, deterministic pairwise distance functions: Hamming distance, percent
identity, and the classic Levenshtein edit distance. No I/O, no network, no
``database``/``api`` imports (§1 layering). See ``analysis.distance.base``
for the documented rules.
"""

from sequence_platform.analysis.distance.base import (
    hamming_distance,
    levenshtein_distance,
    percent_identity,
)

__all__ = [
    "hamming_distance",
    "levenshtein_distance",
    "percent_identity",
]
