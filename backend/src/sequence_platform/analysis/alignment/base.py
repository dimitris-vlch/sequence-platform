"""Pairwise sequence alignment (Stage 6).

Pure functions wrapping :class:`Bio.Align.PairwiseAligner` for global
(Needleman-Wunsch) and local (Smith-Waterman) alignment of two
nucleotide sequences. No I/O, no network, no ``database`` or ``api``
imports (``docs/architecture.md`` §1 layering).

Scoring defaults (nucleotide, not BLOSUM/PAM):

- ``match_score=1.0``
- ``mismatch_score=-1.0``
- ``open_gap_score=-2.0``
- ``extend_gap_score=-0.5``

All four are explicit keyword arguments; the caller can override any of
them.

Edge cases:

- Empty input (either sequence is ``""``) raises ``ValueError``.
- Tied optimal alignments: Biopython returns them in deterministic order;
  we take the first (``alignments[0]``). This is documented as the
  project's tie-breaking convention.
"""

from __future__ import annotations

from dataclasses import dataclass

from Bio.Align import PairwiseAligner

from sequence_platform.analysis.statistics.base import SequenceLike, _normalised
from sequence_platform.models import SeqType

__all__ = [
    "AlignmentResult",
    "global_alignment",
    "local_alignment",
]


@dataclass(frozen=True)
class AlignmentResult:
    """Result of a pairwise alignment.

    Attributes
    ----------
    score:
        Alignment score under the scoring scheme used.
    aligned_a:
        Sequence A with gap characters (``-``) inserted.
    aligned_b:
        Sequence B with gap characters (``-``) inserted.
    start_a:
        0-based start index of the aligned region in sequence A.
    end_a:
        0-based end index (exclusive) of the aligned region in sequence A.
    start_b:
        0-based start index of the aligned region in sequence B.
    end_b:
        0-based end index (exclusive) of the aligned region in sequence B.
    """

    score: float
    aligned_a: str
    aligned_b: str
    start_a: int
    end_a: int
    start_b: int
    end_b: int


def _run_alignment(
    a: SequenceLike,
    b: SequenceLike,
    *,
    mode: str,
    match_score: float,
    mismatch_score: float,
    open_gap_score: float,
    extend_gap_score: float,
) -> AlignmentResult:
    """Shared implementation for global and local alignment."""
    seq_a, _ = _normalised(a, SeqType.DNA)
    seq_b, _ = _normalised(b, SeqType.DNA)

    if not seq_a or not seq_b:
        raise ValueError(
            f"Both sequences must be non-empty (got lengths {len(seq_a)} and {len(seq_b)})"
        )

    aligner = PairwiseAligner()
    aligner.mode = mode
    aligner.match_score = match_score
    aligner.mismatch_score = mismatch_score
    aligner.open_gap_score = open_gap_score
    aligner.extend_gap_score = extend_gap_score

    alignments = aligner.align(seq_a, seq_b)
    best = alignments[0]

    coords = best.coordinates
    return AlignmentResult(
        score=float(best.score),
        aligned_a=str(best[0]),
        aligned_b=str(best[1]),
        start_a=int(coords[0][0]),
        end_a=int(coords[0][-1]),
        start_b=int(coords[1][0]),
        end_b=int(coords[1][-1]),
    )


def global_alignment(
    a: SequenceLike,
    b: SequenceLike,
    *,
    match_score: float = 1.0,
    mismatch_score: float = -1.0,
    open_gap_score: float = -2.0,
    extend_gap_score: float = -0.5,
) -> AlignmentResult:
    """Global (Needleman-Wunsch) alignment of two nucleotide sequences.

    Parameters
    ----------
    a, b:
        ``SequenceRecord`` or plain string. Case is normalised to upper.
    match_score, mismatch_score, open_gap_score, extend_gap_score:
        Scoring parameters (nucleotide defaults; not BLOSUM/PAM).

    Returns
    -------
    AlignmentResult

    Raises
    ------
    ValueError
        If either sequence is empty after normalisation.
    """
    return _run_alignment(
        a,
        b,
        mode="global",
        match_score=match_score,
        mismatch_score=mismatch_score,
        open_gap_score=open_gap_score,
        extend_gap_score=extend_gap_score,
    )


def local_alignment(
    a: SequenceLike,
    b: SequenceLike,
    *,
    match_score: float = 1.0,
    mismatch_score: float = -1.0,
    open_gap_score: float = -2.0,
    extend_gap_score: float = -0.5,
) -> AlignmentResult:
    """Local (Smith-Waterman) alignment of two nucleotide sequences.

    Parameters
    ----------
    a, b:
        ``SequenceRecord`` or plain string. Case is normalised to upper.
    match_score, mismatch_score, open_gap_score, extend_gap_score:
        Scoring parameters (nucleotide defaults; not BLOSUM/PAM).

    Returns
    -------
    AlignmentResult

    Raises
    ------
    ValueError
        If either sequence is empty after normalisation.
    """
    return _run_alignment(
        a,
        b,
        mode="local",
        match_score=match_score,
        mismatch_score=mismatch_score,
        open_gap_score=open_gap_score,
        extend_gap_score=extend_gap_score,
    )
