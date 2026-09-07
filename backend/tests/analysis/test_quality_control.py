"""Known-answer tests for the Stage 4 QC battery.

Expected outcomes are hand-computed against the strict semantics: a
sequence that *exactly meets* a threshold passes that check.
"""

from sequence_platform.analysis import quality_control
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


def test_defaults() -> None:
    assert quality_control.DEFAULT_MIN_LENGTH == 100
    assert quality_control.DEFAULT_MAX_AMBIGUOUS_FRACTION == 0.10
    assert quality_control.DEFAULT_MAX_N_RUN == 10


def test_clean_sequence_passes() -> None:
    report = quality_control.quality_report("ACGT" * 38)  # 152 bp, all standard
    assert report.passed is True
    assert report.issues == []


def test_exactly_at_thresholds_passes() -> None:
    # 90 standard + 10 N = 100 bp: exactly 10.0% ambiguous, exactly a
    # 10-N run, exactly the minimum length. All strict.
    report = quality_control.quality_report("AC" * 45 + "N" * 10)
    assert report.passed is True
    assert report.issues == []


def test_short_sequence() -> None:
    report = quality_control.quality_report("ACGT" * 20)  # 80 bp
    assert report.passed is False
    assert len(report.issues) == 1
    assert "length" in report.issues[0]


def test_ambiguous_exceeds() -> None:
    # 88 standard + 12 N = 100 bp: 12% ambiguous, 12-N run.
    report = quality_control.quality_report("AC" * 44 + "N" * 12)
    assert report.passed is False
    assert len(report.issues) == 2
    assert any("ambiguous" in issue for issue in report.issues)
    assert any("N-run" in issue for issue in report.issues)


def test_n_run_exceeds() -> None:
    # 140 standard + 11 N = 151 bp: 7.3% ambiguous, 11-N run.
    report = quality_control.quality_report("AC" * 70 + "N" * 11)
    assert report.passed is False
    assert len(report.issues) == 1
    assert "N-run" in report.issues[0]


def test_all_ambiguous_record() -> None:
    report = quality_control.quality_report(_record("N" * 22))
    assert report.passed is False
    # Short + fully ambiguous + 22-N run: all three checks fail.
    assert len(report.issues) == 3


def test_threshold_override() -> None:
    report = quality_control.quality_report("ACGT" * 20, min_length=50)
    assert report.passed is True
    assert report.issues == []


def test_empty_sequence() -> None:
    report = quality_control.quality_report("")
    assert report.passed is False
    assert len(report.issues) == 1  # only the length check
    assert "length" in report.issues[0]


def test_string_and_record_agree() -> None:
    sequence = "ACGT" * 20
    from_record = quality_control.quality_report(_record(sequence))
    from_string = quality_control.quality_report(sequence)
    assert from_record == from_string
