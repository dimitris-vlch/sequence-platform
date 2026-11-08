"""Pairwise sequence distance (Stage 5).

Pure functions comparing two nucleotide sequences position-by-position or via
edit distance. No I/O, no network, no ``database`` or ``api`` imports
(``docs/architecture.md`` §1 layering).

Semantics (``docs/architecture.md`` §6, Stage 5):

- All functions upper-case both inputs once, so comparison is case-insensitive,
  and map ``U`` to ``T``, so a DNA record matches its RNA counterpart.
- ``hamming_distance`` and ``percent_identity`` compare the full length and
  therefore require the two sequences to be equal length; they raise
  ``ValueError`` otherwise (they never silently truncate or pad). A match is
  byte-for-byte equality after upper-casing — an ambiguous-vs-ambiguous or
  ambiguous-vs-standard position still counts as a comparison.
- ``levenshtein_distance`` is the classic Levenshtein edit distance
  (insertions / deletions / substitutions, cost 1 each) and works on
  sequences of unequal length.

Ambiguity handling is explicit: ambiguity characters are treated as ordinary
characters. A position matches iff the two characters are byte-for-byte equal
after upper-casing; nothing "smarter" (no IUPAC overlap) is attempted.
"""

from __future__ import annotations

from Bio.Align import PairwiseAligner

from sequence_platform.analysis.statistics.base import SequenceLike, _normalised
from sequence_platform.models import SeqType

__all__ = [
    "MAX_LEVENSHTEIN_CELLS",
    "hamming_distance",
    "levenshtein_distance",
    "percent_identity",
]

#: Upper bound on ``len(a) * len(b)`` for :func:`levenshtein_distance`
#: (≈ two 10 kb sequences, ~0.2 s in Biopython's C dynamic programme — the
#: same bound as pairwise alignment). Larger inputs raise ``ValueError``,
#: which the API maps to 422 instead of blocking the server.
MAX_LEVENSHTEIN_CELLS = 100_000_000


def _upper(record_or_sequence: SequenceLike) -> str:
    """Return the upper-cased sequence text in the DNA alphabet.

    ``U`` is mapped to ``T`` so that a DNA record and its RNA counterpart
    compare as identical rather than mismatching at every T/U position;
    nothing else in either alphabet changes. ``SeqType.DNA`` is a placeholder:
    these functions only read the normalised string.
    """
    return _normalised(record_or_sequence, SeqType.DNA)[0].replace("U", "T")


def _edit_distance_aligner() -> PairwiseAligner:
    """Global aligner whose score is minus the Levenshtein distance.

    Unit cost for a substitution, insertion or deletion. Built per call
    (cheap) rather than shared, since routes run this in a thread pool.
    """
    return PairwiseAligner(
        mode="global",
        match_score=0.0,
        mismatch_score=-1.0,
        open_gap_score=-1.0,
        extend_gap_score=-1.0,
    )


def hamming_distance(record_a: SequenceLike, record_b: SequenceLike) -> int:
    """Number of positions at which two equal-length sequences differ.

    Parameters
    ----------
    record_a, record_b:
        Nucleotide sequence(s), each a raw string or a
        :class:`~sequence_platform.models.SequenceRecord`.

    Raises
    ------
    ValueError
        If the two sequences differ in length. Hamming distance is only
        defined for equal-length inputs; nothing is truncated or padded.

    Returns
    -------
    int
        The count of positions with differing (upper-cased) characters.
        Two empty sequences give ``0``.
    """
    seq_a = _upper(record_a)
    seq_b = _upper(record_b)
    if len(seq_a) != len(seq_b):
        raise ValueError(
            "hamming_distance requires equal-length sequences "
            f"(got {len(seq_a)} and {len(seq_b)})"
        )
    return sum(ch_a != ch_b for ch_a, ch_b in zip(seq_a, seq_b, strict=True))


def percent_identity(record_a: SequenceLike, record_b: SequenceLike) -> float:
    """Percentage of positions at which two equal-length sequences match.

    Defined as ``100 * matches / length`` over the full length, where a match
    is byte-for-byte equality after upper-casing (so an ambiguous character
    only matches the same character — e.g. "N" matches "N" but not "A").

    Two empty sequences are vacuously identical and return ``100.0``.

    Parameters
    ----------
    record_a, record_b:
        Nucleotide sequence(s), each a raw string or a
        :class:`~sequence_platform.models.SequenceRecord`.

    Raises
    ------
    ValueError
        If the two sequences differ in length.

    Returns
    -------
    float
        The percentage of matching positions, rounded to 2 decimal places.
    """
    seq_a = _upper(record_a)
    seq_b = _upper(record_b)
    if len(seq_a) != len(seq_b):
        raise ValueError(
            "percent_identity requires equal-length sequences "
            f"(got {len(seq_a)} and {len(seq_b)})"
        )
    length = len(seq_a)
    if length == 0:
        return 100.0
    matches = sum(ch_a == ch_b for ch_a, ch_b in zip(seq_a, seq_b, strict=True))
    return round(100.0 * matches / length, 2)


def levenshtein_distance(record_a: SequenceLike, record_b: SequenceLike) -> int:
    """Classic Levenshtein edit distance between two sequences.

    Counts the minimum number of single-character insertions, deletions, or
    substitutions (each costing 1) to transform one sequence into the other.
    Works on sequences of unequal length. Two empty sequences give ``0``.

    Parameters
    ----------
    record_a, record_b:
        Nucleotide sequence(s), each a raw string or a
        :class:`~sequence_platform.models.SequenceRecord`.

    Returns
    -------
    int
        The minimum edit distance (unit costs for insert / delete / substitute).

    Raises
    ------
    ValueError
        If ``len(a) * len(b)`` exceeds :data:`MAX_LEVENSHTEIN_CELLS`. The
        dynamic programme is quadratic in time, so an
        unbounded input (e.g. two whole chromosomes) would stall the server.

    Notes
    -----
    Classic O(n·m)-time dynamic programme, computed as the score of a global
    alignment with unit costs in Biopython's C aligner (score-only, so
    memory is linear); the result equals the textbook Levenshtein distance.
    """
    seq_a = _upper(record_a)
    seq_b = _upper(record_b)
    cells = len(seq_a) * len(seq_b)
    if cells > MAX_LEVENSHTEIN_CELLS:
        raise ValueError(
            f"sequences too long for edit distance ({len(seq_a)} x {len(seq_b)} "
            f"= {cells} cells; limit {MAX_LEVENSHTEIN_CELLS})"
        )
    if not seq_a or not seq_b:
        return max(len(seq_a), len(seq_b))
    # Score-only global alignment in Biopython's C code: same O(n*m) time
    # as the textbook dynamic programme, linear memory, no traceback, and
    # ~50x faster than the former pure-Python loop.
    return int(round(-_edit_distance_aligner().score(seq_a, seq_b)))
