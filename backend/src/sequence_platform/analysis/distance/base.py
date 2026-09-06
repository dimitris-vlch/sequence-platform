"""Pairwise sequence distance (Stage 5).

Pure functions comparing two nucleotide sequences position-by-position or via
edit distance. No I/O, no network, no ``database`` or ``api`` imports
(``docs/architecture.md`` §1 layering).

Semantics (``docs/architecture.md`` §6, Stage 5):

- All functions upper-case both inputs once, so comparison is case-insensitive.
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

from sequence_platform.analysis.statistics.base import SequenceLike, _normalised
from sequence_platform.models import SeqType

__all__ = [
    "hamming_distance",
    "levenshtein_distance",
    "percent_identity",
]


def _upper(record_or_sequence: SequenceLike) -> str:
    """Return the upper-cased sequence text (reuses the Stage 4 normaliser).

    ``SeqType.DNA`` is a placeholder here: these functions only read the
    normalised string and do not validate against any alphabet, so the
    seq_type argument is unused.
    """
    return _normalised(record_or_sequence, SeqType.DNA)[0]


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

    Notes
    -----
    Implemented directly with a full O(n·m) dynamic-programming table —
    intentionally not optimised, and with no third-party dependency.
    """
    seq_a = _upper(record_a)
    seq_b = _upper(record_b)
    n, m = len(seq_a), len(seq_b)

    # dp[i][j] = edit distance between seq_a[:i] and seq_b[:j].
    # dp[i][0] == i (delete i characters); dp[0][j] == j (insert j).
    dp = [[j for j in range(m + 1)]] + [[i] + [0] * m for i in range(1, n + 1)]

    for i in range(1, n + 1):
        a_char = seq_a[i - 1]
        row = dp[i]
        prev_row = dp[i - 1]
        for j in range(1, m + 1):
            if a_char == seq_b[j - 1]:
                row[j] = prev_row[j - 1]
            else:
                row[j] = 1 + min(prev_row[j], row[j - 1], prev_row[j - 1])

    return dp[n][m]

