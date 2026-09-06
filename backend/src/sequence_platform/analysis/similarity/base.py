"""Pairwise sequence similarity (Stage 5).

Pure functions built on top of the :mod:`sequence_platform.analysis.distance`
metrics. No I/O, no network, no ``database`` or ``api`` imports
(``docs/architecture.md`` §1 layering).

All functions upper-case both inputs once, so comparison is case-insensitive.
Ambiguity handling is the same explicit convention as in the distance module:
ambiguity characters are treated as ordinary characters (byte-for-byte
equality / byte-for-byte k-mers).
"""

from __future__ import annotations

from dataclasses import dataclass

from sequence_platform.analysis.distance.base import (
    hamming_distance,
    levenshtein_distance,
    percent_identity,
)
from sequence_platform.analysis.statistics.base import SequenceLike, _normalised
from sequence_platform.models import SeqType

__all__ = [
    "ComparisonReport",
    "compare",
    "jaccard_kmer_similarity",
    "normalized_edit_similarity",
]


def _upper(record_or_sequence: SequenceLike) -> str:
    """Return the upper-cased sequence text (reuses the Stage 4 normaliser).

    ``SeqType.DNA`` is a placeholder: these functions only read the normalised
    string and do not validate against any alphabet, so seq_type is unused.
    """
    return _normalised(record_or_sequence, SeqType.DNA)[0]


@dataclass
class ComparisonReport:
    """Aggregated pairwise comparison of two sequences.

    ``hamming_distance`` and ``percent_identity`` are ``None`` whenever the two
    sequences differ in length (those metrics are only defined for equal-length
    inputs); the edit-distance and k-mer metrics always apply.
    """

    length_a: int
    length_b: int
    hamming_distance: int | None
    percent_identity: float | None
    levenshtein_distance: int
    normalized_edit_similarity: float
    jaccard_kmer_similarity: float


def normalized_edit_similarity(record_a: SequenceLike, record_b: SequenceLike) -> float:
    """Similarity derived from the normalised Levenshtein distance.

    Defined as ``100 * (1 - levenshtein_distance(a, b) / max(len(a), len(b)))``,
    capped to ``[0, 100]`` and rounded to 2 decimal places. Two empty sequences
    give ``100.0`` (the max-length denominator would otherwise be zero).
    """
    seq_a = _upper(record_a)
    seq_b = _upper(record_b)
    max_len = max(len(seq_a), len(seq_b))
    if max_len == 0:
        return 100.0
    distance = levenshtein_distance(seq_a, seq_b)
    similarity = 100.0 * (1.0 - distance / max_len)
    return round(min(100.0, max(0.0, similarity)), 2)


def jaccard_kmer_similarity(
    record_a: SequenceLike, record_b: SequenceLike, *, k: int = 4
) -> float:
    """Jaccard index (as a percentage) over the k-mer sets of two sequences.

    The k-mers of a sequence are its contiguous substrings of length ``k``
    (``len(sequence) - k + 1`` of them, counted with multiplicity removed via
    a set). The Jaccard index is ``|A ∩ B| / |A ∪ B|``; the result is expressed
    as a percentage and rounded to 2 decimal places.

    Two empty sequences give ``100.0`` (both k-mer sets are empty; the union
    would otherwise be zero and the index undefined). If exactly one sequence
    is empty the result is ``0.0`` (empty set vs a non-empty set).

    Raises
    ------
    ValueError
        If ``k < 1``, or if either sequence is non-empty and shorter than ``k``
        (so its k-mer set cannot be formed).
    """
    if k < 1:
        raise ValueError(f"k must be a positive integer (got {k})")

    seq_a = _upper(record_a)
    seq_b = _upper(record_b)

    if not seq_a and not seq_b:
        return 100.0

    for label, seq in (("a", seq_a), ("b", seq_b)):
        if seq and len(seq) < k:
            raise ValueError(
                f"sequence {label} (length {len(seq)}) is shorter than k={k}"
            )

    kmers_a = {seq_a[i : i + k] for i in range(len(seq_a) - k + 1)}
    kmers_b = {seq_b[i : i + k] for i in range(len(seq_b) - k + 1)}
    union = len(kmers_a | kmers_b)
    if union == 0:
        return 100.0
    return round(100.0 * len(kmers_a & kmers_b) / union, 2)


def compare(
    record_a: SequenceLike, record_b: SequenceLike, *, k: int = 4
) -> ComparisonReport:
    """Compute all pairwise metrics for two sequences in one report.

    Aggregates :func:`~sequence_platform.analysis.distance.hamming_distance`,
    :func:`~sequence_platform.analysis.distance.percent_identity`,
    :func:`~sequence_platform.analysis.distance.levenshtein_distance`,
    :func:`normalized_edit_similarity`, and :func:`jaccard_kmer_similarity`
    into a single :class:`ComparisonReport`.

    ``hamming_distance`` and ``percent_identity`` are ``None`` when the two
    sequences differ in length. :func:`jaccard_kmer_similarity` may raise
    ``ValueError`` (propagated) if ``k < 1`` or a sequence is non-empty but
    shorter than ``k``.
    """
    seq_a = _upper(record_a)
    seq_b = _upper(record_b)
    length_a, length_b = len(seq_a), len(seq_b)
    equal_length = length_a == length_b

    return ComparisonReport(
        length_a=length_a,
        length_b=length_b,
        hamming_distance=hamming_distance(seq_a, seq_b) if equal_length else None,
        percent_identity=percent_identity(seq_a, seq_b) if equal_length else None,
        levenshtein_distance=levenshtein_distance(seq_a, seq_b),
        normalized_edit_similarity=normalized_edit_similarity(seq_a, seq_b),
        jaccard_kmer_similarity=jaccard_kmer_similarity(seq_a, seq_b, k=k),
    )
