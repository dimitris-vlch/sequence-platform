"""Regression tests for bugs found in the October 2026 code review."""

from __future__ import annotations

import pytest

from sequence_platform.analysis.alignment import base as alignment_base
from sequence_platform.analysis.distance import base as distance_base
from sequence_platform.analysis.similarity import compare
from sequence_platform.models import SeqType, SequenceRecord
from sequence_platform.validation import is_valid_sequence, validate_sequence


@pytest.mark.parametrize("seq_type", [SeqType.DNA, SeqType.RNA])
def test_record_valid_bases_match_validator(seq_type: SeqType) -> None:
    record = SequenceRecord(accession="x", sequence="A", seq_type=seq_type)
    for code in "HV":
        assert code in record.valid_bases
        assert is_valid_sequence(code, seq_type)


def test_whitespace_of_every_kind_is_stripped() -> None:
    assert validate_sequence("ac\tgt\r\nNN ") == "ACGTNN"
    assert SequenceRecord(accession="x", sequence="ac\tg\r\nt").sequence == "ACGT"


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("", "", 0),
        ("", "ACG", 3),
        ("KITTEN", "SITTING", 3),
        ("ACGT", "TGCA", 4),
        ("GATTACA", "GCATGCU", 4),
    ],
)
def test_levenshtein_two_row_matches_known_values(
    a: str, b: str, expected: int
) -> None:
    assert distance_base.levenshtein_distance(a, b) == expected
    assert distance_base.levenshtein_distance(b, a) == expected


def test_levenshtein_rejects_oversized_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(distance_base, "MAX_LEVENSHTEIN_CELLS", 15)
    assert distance_base.levenshtein_distance("ACGT", "ACG") == 1  # 12 cells
    with pytest.raises(ValueError, match="too long"):
        distance_base.levenshtein_distance("ACGT", "ACGT")  # 16 cells


def test_compare_propagates_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(distance_base, "MAX_LEVENSHTEIN_CELLS", 15)
    with pytest.raises(ValueError, match="too long"):
        compare("ACGTACGT", "ACGTACGT", k=2)


def test_alignment_rejects_oversized_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(alignment_base, "MAX_ALIGNMENT_CELLS", 15)
    with pytest.raises(ValueError, match="too long"):
        alignment_base.global_alignment("ACGT", "ACGT")
