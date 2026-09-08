"""Known-answer tests for the pure Stage 6 alignment functions.

Values are hand-computed from the scoring scheme (match=1, mismatch=-1,
open_gap=-2, extend_gap=-0.5) and cross-checked against Biopython
``PairwiseAligner`` output.
"""

import pytest

from sequence_platform.analysis.alignment import (
    AlignmentResult,
    global_alignment,
    local_alignment,
)
from sequence_platform.models import SeqType, SequenceRecord


def _record(sequence: str) -> SequenceRecord:
    return SequenceRecord(
        accession="T_1",
        sequence=sequence,
        seq_type=SeqType.DNA,
        title="T_1",
        description="test record",
        source_database="",
        metadata={},
    )


# --- global_alignment -----------------------------------------------------


def test_global_identical_sequences():
    """ACGT vs ACGT: 4 matches, score = 4.0."""
    result = global_alignment("ACGT", "ACGT")
    assert result.score == pytest.approx(4.0)
    assert result.aligned_a == "ACGT"
    assert result.aligned_b == "ACGT"
    assert result.start_a == 0
    assert result.end_a == 4
    assert result.start_b == 0
    assert result.end_b == 4


def test_global_single_mismatch():
    """ACGT vs ACGA: 3 matches + 1 mismatch = 3 - 1 = 2.0."""
    result = global_alignment("ACGT", "ACGA")
    assert result.score == pytest.approx(2.0)
    assert result.aligned_a == "ACGT"
    assert result.aligned_b == "ACGA"
    assert result.start_a == 0
    assert result.end_a == 4
    assert result.start_b == 0
    assert result.end_b == 4


def test_global_unequal_length_introduces_gap():
    """ACGT vs ACG: 3 matches + 1 gap (open=-2, no extension) = 3 - 2 = 1.0.

    Biopython aligns the gap at the end: ACGT vs ACG-.
    """
    result = global_alignment("ACGT", "ACG")
    assert result.score == pytest.approx(1.0)
    assert result.aligned_a == "ACGT"
    assert result.aligned_b == "ACG-"
    assert result.start_a == 0
    assert result.end_a == 4
    assert result.start_b == 0
    assert result.end_b == 3


def test_global_is_case_insensitive():
    """Lowercase input is upper-cased before alignment."""
    result = global_alignment("acgt", "ACGA")
    assert result.score == pytest.approx(2.0)
    assert result.aligned_a == "ACGT"
    assert result.aligned_b == "ACGA"


def test_global_empty_input_raises():
    with pytest.raises(ValueError, match="empty"):
        global_alignment("", "ACGT")
    with pytest.raises(ValueError, match="empty"):
        global_alignment("ACGT", "")
    with pytest.raises(ValueError, match="empty"):
        global_alignment("", "")


def test_global_accepts_sequence_records():
    result = global_alignment(_record("ACGT"), _record("ACGA"))
    assert result.score == pytest.approx(2.0)
    assert result.aligned_a == "ACGT"
    assert result.aligned_b == "ACGA"


def test_global_custom_scores():
    """ACGT vs ACGA with match=2, mismatch=-2: 3*2 + 1*(-2) = 4.0."""
    result = global_alignment("ACGT", "ACGA", match_score=2.0, mismatch_score=-2.0)
    assert result.score == pytest.approx(4.0)


def test_global_result_is_dataclass():
    result = global_alignment("ACGT", "ACGT")
    assert isinstance(result, AlignmentResult)
    assert isinstance(result.score, float)
    assert isinstance(result.aligned_a, str)
    assert isinstance(result.start_a, int)


# --- local_alignment ------------------------------------------------------


def test_local_identical_sequences():
    """ACGT vs ACGT: local finds the full 4 bp, score = 4.0."""
    result = local_alignment("ACGT", "ACGT")
    assert result.score == pytest.approx(4.0)
    assert result.aligned_a == "ACGT"
    assert result.aligned_b == "ACGT"
    assert result.start_a == 0
    assert result.end_a == 4
    assert result.start_b == 0
    assert result.end_b == 4


def test_local_finds_best_subregion():
    """NNNNACGTNNNN vs ACGT: local alignment locks onto the ACGT sub-region.

    The N's score 0 (neither match nor mismatch), so the best local
    alignment is just ACGT vs ACGT at positions 4-8 of seq A.
    """
    result = local_alignment("NNNNACGTNNNN", "ACGT")
    assert result.score == pytest.approx(4.0)
    assert result.aligned_a == "ACGT"
    assert result.aligned_b == "ACGT"
    assert result.start_a == 4
    assert result.end_a == 8
    assert result.start_b == 0
    assert result.end_b == 4


def test_local_unequal_length():
    """ACGTACGT vs ACGT: local finds the first ACGT (positions 0-4).

    Biopython returns 2 equally-scored alignments; we take the first.
    """
    result = local_alignment("ACGTACGT", "ACGT")
    assert result.score == pytest.approx(4.0)
    assert result.aligned_a == "ACGT"
    assert result.aligned_b == "ACGT"
    assert result.start_a == 0
    assert result.end_a == 4
    assert result.start_b == 0
    assert result.end_b == 4


def test_local_empty_input_raises():
    with pytest.raises(ValueError, match="empty"):
        local_alignment("", "ACGT")
    with pytest.raises(ValueError, match="empty"):
        local_alignment("ACGT", "")


def test_local_is_case_insensitive():
    result = local_alignment("nnnnacgtnnnn", "ACGT")
    assert result.score == pytest.approx(4.0)
    assert result.aligned_a == "ACGT"
    assert result.aligned_b == "ACGT"
    assert result.start_a == 4
    assert result.end_a == 8


def test_local_accepts_sequence_records():
    result = local_alignment(_record("NNNNACGTNNNN"), _record("ACGT"))
    assert result.score == pytest.approx(4.0)
    assert result.start_a == 4
    assert result.end_a == 8
