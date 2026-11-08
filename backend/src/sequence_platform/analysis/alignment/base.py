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
- Non-finite scores, or a positive gap score, raise ``ValueError``.
- A local alignment with no positive-scoring pair returns the empty
  alignment (score 0, empty strings, all coordinates 0).
- Aligning a DNA record against an RNA record compares both in the DNA
  alphabet (``U`` -> ``T``), so the gapped strings show ``T``.
- Tied optimal alignments: Biopython returns them in deterministic order;
  we take the first (``alignments[0]``). This is documented as the
  project's tie-breaking convention.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from Bio.Align import PairwiseAligner

from sequence_platform.analysis.statistics.base import SequenceLike, _normalised
from sequence_platform.models import SeqType

__all__ = [
    "MAX_ALIGNMENT_CELLS",
    "AlignmentResult",
    "global_alignment",
    "local_alignment",
]

#: Upper bound on ``len(a) * len(b)`` for one alignment (≈ two 10 kb
#: sequences, a few seconds in Biopython's C aligner). The dynamic programme
#: is quadratic in time and traceback memory, so larger inputs raise
#: ``ValueError`` (mapped to 422) instead of exhausting the server.
MAX_ALIGNMENT_CELLS = 100_000_000


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
    scores = {
        "match_score": match_score,
        "mismatch_score": mismatch_score,
        "open_gap_score": open_gap_score,
        "extend_gap_score": extend_gap_score,
    }
    for label, value in scores.items():
        # Biopython's C aligner segfaults on an infinite gap score (taking the
        # whole server process down) and silently produces garbage for NaN,
        # so non-finite scores are refused before they reach it.
        if not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number (got {value})")
    for label in ("open_gap_score", "extend_gap_score"):
        # A positive gap score rewards gaps: the optimum becomes "gap
        # everything" with an inflated score, which is never meaningful.
        if scores[label] > 0:
            raise ValueError(f"{label} must be <= 0 (got {scores[label]})")

    seq_a, type_a = _normalised(a, SeqType.DNA)
    seq_b, type_b = _normalised(b, SeqType.DNA)
    if type_a != type_b:
        # DNA vs RNA: compare in the DNA alphabet, so T and U pair as the
        # same base instead of scoring every T/U column as a mismatch.
        seq_a = seq_a.replace("U", "T")
        seq_b = seq_b.replace("U", "T")

    if not seq_a or not seq_b:
        raise ValueError(
            f"Both sequences must be non-empty (got lengths {len(seq_a)} and {len(seq_b)})"
        )
    cells = len(seq_a) * len(seq_b)
    if cells > MAX_ALIGNMENT_CELLS:
        raise ValueError(
            f"sequences too long for pairwise alignment ({len(seq_a)} x "
            f"{len(seq_b)} = {cells} cells; limit {MAX_ALIGNMENT_CELLS})"
        )

    aligner = PairwiseAligner()
    aligner.mode = mode
    aligner.match_score = match_score
    aligner.mismatch_score = mismatch_score
    aligner.open_gap_score = open_gap_score
    aligner.extend_gap_score = extend_gap_score

    alignments = aligner.align(seq_a, seq_b)
    try:
        best = alignments[0]
    except IndexError:
        # Local mode with no positive-scoring pair (e.g. "AAAA" vs "TTTT"):
        # Biopython yields no alignment at all. The Smith-Waterman optimum is
        # then the empty alignment, score 0.
        return AlignmentResult(
            score=0.0,
            aligned_a="",
            aligned_b="",
            start_a=0,
            end_a=0,
            start_b=0,
            end_b=0,
        )

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
