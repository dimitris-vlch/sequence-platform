"""Known-answer tests for the pure statistics functions (Stage 4).

Every expected value is hand-computed from the documented rules (§6
Stage 4): GC content relative to standard bases only, base composition
relative to the full length, N-runs = consecutive ``N`` characters only.
"""

import pytest

from sequence_platform.analysis import statistics
from sequence_platform.models import SeqType, SequenceRecord


def _record(sequence: str, *, seq_type: SeqType = SeqType.DNA) -> SequenceRecord:
    return SequenceRecord(
        accession="TEST",
        sequence=sequence,
        seq_type=seq_type,
        title="test",
        description="test",
        source_database="",
        metadata={},
    )


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        ("ACGT", 4),
        ("acgt", 4),
        ("ACGTACGT", 8),
        ("ACGTN", 5),
        ("", 0),
    ],
)
def test_sequence_length(sequence: str, expected: int) -> None:
    assert statistics.sequence_length(sequence) == expected


def test_sequence_length_record() -> None:
    assert statistics.sequence_length(_record("ACGTACGT")) == 8
    assert statistics.sequence_length(_record("acgt")) == 4


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        ("ACGT", 50.0),
        ("GGGG", 100.0),
        ("ATAT", 0.0),
        ("ACG", 66.67),
        ("ACGTN", 50.0),
        ("ACGTNNN", 50.0),
        ("NNNN", None),
        ("RYSWKMBDHVN", None),
        ("", None),
    ],
)
def test_gc_content(sequence: str, expected: float | None) -> None:
    assert statistics.gc_content(sequence) == expected


def test_gc_content_rna_alphabet() -> None:
    assert statistics.gc_content(_record("ACGU", seq_type=SeqType.RNA)) == 50.0
    assert statistics.gc_content("ACGU", seq_type=SeqType.RNA) == 50.0
    # The same string treated as DNA: U is not a standard DNA base.
    assert statistics.gc_content("ACGU") == 66.67


def test_base_composition_uniform() -> None:
    assert statistics.base_composition("ACGTACGT") == {
        "A": 25.0,
        "C": 25.0,
        "G": 25.0,
        "T": 25.0,
        "ambiguous": 0.0,
    }


def test_base_composition_rna_keys() -> None:
    result = statistics.base_composition(_record("ACGU", seq_type=SeqType.RNA))
    assert set(result) == {"A", "C", "G", "U", "ambiguous"}
    assert result["U"] == 25.0


def test_base_composition_ambiguous_bucket() -> None:
    assert statistics.base_composition("ACGTN") == {
        "A": 20.0,
        "C": 20.0,
        "G": 20.0,
        "T": 20.0,
        "ambiguous": 20.0,
    }


def test_base_composition_all_nucleotides() -> None:
    # The 15-char IUPAC showcase: 1 of each standard + all 11 codes.
    result = statistics.base_composition("ACGTRYSWKMBDHVN")
    assert result["A"] == result["C"] == result["G"] == result["T"] == 6.67
    assert result["ambiguous"] == 73.33


def test_base_composition_empty() -> None:
    assert statistics.base_composition("") == {
        "A": 0.0,
        "C": 0.0,
        "G": 0.0,
        "T": 0.0,
        "ambiguous": 0.0,
    }


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        ("ACGT", 0),
        ("ACGTN", 1),
        ("NNNN", 4),
        ("RYSWKMBDHVN", 11),
        ("X", 0),
        ("", 0),
    ],
)
def test_ambiguous_base_count(sequence: str, expected: int) -> None:
    assert statistics.ambiguous_base_count(sequence) == expected


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        ("ACGT", 0.0),
        ("ACGTN", 20.0),
        ("NNNN", 100.0),
        ("ACGTRYSWKMBDHVN", 73.33),
        ("", 0.0),
    ],
)
def test_ambiguous_base_percentage(sequence: str, expected: float) -> None:
    assert statistics.ambiguous_base_percentage(sequence) == expected


@pytest.mark.parametrize(
    ("sequence", "runs", "longest"),
    [
        ("", 0, 0),
        ("ACGT", 0, 0),
        ("N", 1, 1),
        ("NNNN", 1, 4),
        ("NNACGTNNN", 2, 3),
        ("NNGGNN", 2, 2),
        ("RYSW", 0, 0),
    ],
)
def test_n_runs(sequence: str, runs: int, longest: int) -> None:
    assert statistics.n_run_count(sequence) == runs
    assert statistics.longest_n_run(sequence) == longest


def test_record_and_string_agree() -> None:
    record = _record("ACGTNACGT")
    assert statistics.sequence_length(record) == statistics.sequence_length("ACGTNACGT")
    assert statistics.gc_content(record) == statistics.gc_content("ACGTNACGT")
    assert statistics.base_composition(record) == statistics.base_composition(
        "ACGTNACGT"
    )
