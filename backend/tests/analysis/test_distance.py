"""Known-answer tests for the pure Stage 5 distance functions.

Values are hand-computed (no reference library); ambiguous characters are
compared byte-for-byte after upper-casing, per the documented Stage 5 rule.
"""

import pytest

from sequence_platform.analysis.distance import (
    hamming_distance,
    levenshtein_distance,
    percent_identity,
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


# --- hamming_distance -----------------------------------------------------


def test_hamming_identical_is_zero():
    assert hamming_distance("ACGT", "ACGT") == 0


def test_hamming_is_case_insensitive():
    assert hamming_distance("ACGT", "acgt") == 0


def test_hamming_counts_mismatching_positions():
    assert hamming_distance("ACGT", "ATGT") == 1
    assert hamming_distance("ACGT", "TAGC") == 3
    assert hamming_distance("ACGA", "AGCT") == 3


def test_hamming_two_empty_is_zero():
    assert hamming_distance("", "") == 0


def test_hamming_unequal_length_raises():
    with pytest.raises(ValueError):
        hamming_distance("AC", "ATG")


def test_hamming_accepts_sequence_records():
    assert hamming_distance(_record("ACGT"), _record("ATGT")) == 1


# --- percent_identity -----------------------------------------------------


def test_percent_identity_all_match():
    assert percent_identity("ACGT", "ACGT") == 100.0


def test_percent_identity_partial_match():
    assert percent_identity("ACGT", "ATGT") == pytest.approx(75.0)


def test_percent_identity_no_match():
    assert percent_identity("AC", "TT") == 0.0


def test_percent_identity_two_empty_is_hundred():
    assert percent_identity("", "") == 100.0


def test_percent_identity_unequal_length_raises():
    with pytest.raises(ValueError):
        percent_identity("AC", "ATG")


# --- levenshtein_distance -------------------------------------------------


def test_levenshtein_identical_is_zero():
    assert levenshtein_distance("ACGT", "ACGT") == 0


def test_levenshtein_single_substitution():
    assert levenshtein_distance("ACGT", "ATGT") == 1


def test_levenshtein_insertion_and_deletion():
    assert levenshtein_distance("ACG", "ACGT") == 1
    assert levenshtein_distance("ACGT", "ACG") == 1


def test_levenshtein_mixed_edit_distance_two():
    assert levenshtein_distance("AC", "ATG") == 2


def test_levenshtein_against_empty_is_length():
    assert levenshtein_distance("", "ACGT") == 4
    assert levenshtein_distance("ACGT", "") == 4


def test_levenshtein_two_empty_is_zero():
    assert levenshtein_distance("", "") == 0


def test_levenshtein_is_case_insensitive():
    assert levenshtein_distance("ACGT", "atgt") == 1
