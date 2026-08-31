"""Tests for the NCBI FASTA formatter and parser.

These tests pin the deterministic behaviour of ``format_fasta`` and
``parse_fasta``: exact header strings, line wrapping, case
normalisation, record joining, ordering, round trips and validation
errors. The same representation is shared with the ENA module; the
``all_nucleotides`` and ``ambiguous_reference`` fixtures from the
top-level ``conftest.py`` supply biologically valid reference records.
"""

import pytest

from sequence_platform.database import ncbi
from sequence_platform.database.ncbi.fasta import (
    FASTA_LINE_WIDTH,
    _header_for,
    _split_title,
    format_fasta,
    parse_fasta,
)
from sequence_platform.database.registry import SUPPORTED_DATABASES
from sequence_platform.models import SeqType, SequenceRecord
from sequence_platform.validation import SequenceValidationError


def test_header_uses_accession_when_description_is_blank() -> None:
    record = SequenceRecord(accession="x", description="", sequence="ACGT")
    assert _header_for(record) == "x"


def test_header_joins_accession_and_description() -> None:
    record = SequenceRecord(accession="one", description="first entry", sequence="ACGT")
    assert _header_for(record) == "one first entry"


def test_header_does_not_duplicate_accession_prefix() -> None:
    record = SequenceRecord(
        accession="long", description="long sequence", sequence="ACGT"
    )
    assert _header_for(record) == "long sequence"


@pytest.mark.parametrize("description", ["", "   "])
def test_blank_description_falls_back_to_accession(description: str) -> None:
    record = SequenceRecord(accession="acc", description=description, sequence="ACGT")
    assert _header_for(record) == "acc"


@pytest.mark.parametrize(
    ("title", "expected_accession", "expected_description"),
    [
        ("", "", ""),
        ("   ", "", ""),
        ("x", "x", ""),
        ("x y z", "x", "y z"),
        ("x  y   z  ", "x", "y   z"),
    ],
)
def test_split_title(
    title: str, expected_accession: str, expected_description: str
) -> None:
    assert _split_title(title) == (expected_accession, expected_description)


def test_format_fasta_wraps_sequences_at_default_width() -> None:
    record = SequenceRecord(
        accession="long", description="long sequence", sequence="ACGT" * 17
    )
    text = format_fasta([record])
    lines = text.splitlines()
    assert lines[0] == ">long sequence"
    assert [len(line) for line in lines] == [14, FASTA_LINE_WIDTH, 8]
    assert text == f">long sequence\n{'ACGT' * 15}\n{'ACGT' * 2}\n"


def test_format_fasta_uses_accession_alone_for_blank_description() -> None:
    record = SequenceRecord(accession="x", description="", sequence="ACGT")
    assert format_fasta([record]) == ">x\nACGT\n"


def test_format_fasta_keeps_header_for_empty_sequence() -> None:
    record = SequenceRecord(accession="y", description="y desc", sequence="")
    assert format_fasta([record]) == ">y desc\n"


def test_format_fasta_preserves_record_order() -> None:
    records = [
        SequenceRecord(accession="one", description="first entry", sequence="ACGT"),
        SequenceRecord(accession="two", description="second entry", sequence="GGGG"),
    ]
    assert format_fasta(records) == ">one first entry\nACGT\n>two second entry\nGGGG\n"


def test_to_fasta_matches_format_fasta_by_default() -> None:
    record = SequenceRecord(accession="x", description="", sequence="ACGTACGT")
    assert record.to_fasta() == ">x\nACGTACGT\n"
    assert record.to_fasta() == format_fasta([record])


def test_to_fasta_delegates_wrap_to_format_fasta() -> None:
    record = SequenceRecord(accession="x", description="", sequence="ACGTACGT")
    assert record.to_fasta(wrap=5) == ">x\nACGTA\nCGT\n"


def test_parse_fasta_builds_records_from_wrapped_lines() -> None:
    records = parse_fasta(">abc test sequence\nACGT\nACGT\n")
    assert records[0].accession == "abc"
    assert records[0].description == "test sequence"
    assert records[0].title == "abc test sequence"
    assert records[0].sequence == "ACGTACGT"
    assert len(records[0].sequence) == 8
    assert records[0].seq_type is SeqType.DNA
    assert records[0].source_database == ""
    assert records[0].metadata == {}


def test_parse_fasta_joins_wrapped_lines_into_one_sequence() -> None:
    doc = ">ref\n" + "A" * 60 + "\n" + "G" * 61 + "\n"
    records = parse_fasta(doc)
    assert len(records) == 1
    assert records[0].sequence == "A" * 60 + "G" * 61
    assert len(records[0].sequence) == 121


def test_parse_fasta_uppercases_and_strips_sequence_lines() -> None:
    records = parse_fasta(">crlf\nacgt\r\nacgt  \r\n")
    assert records[0].sequence == "ACGTACGT"
    assert len(records[0].sequence) == 8


def test_parse_fasta_reads_title_without_description() -> None:
    records = parse_fasta(">alpha first line\nACGT\n>beta\n")
    assert [(r.accession, r.description, r.sequence) for r in records] == [
        ("alpha", "first line", "ACGT"),
        ("beta", "", ""),
    ]


def test_parse_fasta_returns_no_records_for_empty_input() -> None:
    assert parse_fasta("") == []


def test_parse_fasta_returns_no_records_for_blank_input() -> None:
    assert parse_fasta("\n   \n") == []


def test_parse_fasta_rejects_invalid_nucleotide() -> None:
    with pytest.raises(
        SequenceValidationError, match="invalid characters for dna sequence"
    ):
        parse_fasta(">bad\nACGTZ")


def test_parse_fasta_rejects_rna_character_for_dna_record() -> None:
    with pytest.raises(
        SequenceValidationError, match="invalid characters for dna sequence"
    ):
        parse_fasta(">rna\nACGU")


def test_parse_fasta_rejects_empty_accession_with_record_position() -> None:
    with pytest.raises(ValueError, match="empty accession"):
        parse_fasta(">\nACGT")


def test_format_then_parse_round_trips_records() -> None:
    records = [
        SequenceRecord(accession="one", description="first entry", sequence="ACGT"),
        SequenceRecord(accession="two", description="second", sequence="ACGTRYSWK"),
    ]
    parsed = parse_fasta(format_fasta(records))
    assert [(r.accession, r.description, r.sequence) for r in parsed] == [
        ("one", "first entry", "ACGT"),
        ("two", "second", "ACGTRYSWK"),
    ]
    assert [r.title for r in parsed] == ["one first entry", "two second"]


def test_fixture_records_round_trip_through_fasta(
    all_nucleotides: SequenceRecord, ambiguous_reference: SequenceRecord
) -> None:
    records = [all_nucleotides, ambiguous_reference]
    assert parse_fasta(format_fasta(records)) == records


def test_fasta_utilities_are_shared_across_supported_databases() -> None:
    assert ncbi.format_fasta is format_fasta
    assert ncbi.parse_fasta is parse_fasta
    assert ncbi.FASTA_LINE_WIDTH is FASTA_LINE_WIDTH
    assert ncbi.SUPPORTED_DATABASES is SUPPORTED_DATABASES
