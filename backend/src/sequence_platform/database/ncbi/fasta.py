"""FASTA parsing and formatting built on Biopython.

This module is the single place that converts between the platform's
``SequenceRecord`` domain objects and the FASTA text format.

All external-format I/O must live here. The rest of the codebase works only
with ``SequenceRecord`` instances and never touches raw FASTA text.

Parsing and writing are deliberately implemented on top of Biopython rather
than by hand: Biopython's ``SeqIO`` is the most battle-tested FASTA
implementation in Python and already handles the full range of format
irregularities (wrapped sequence lines, missing trailing newlines, unusual
titles, BOMs, ...). Building a second, private parser/writer would only
create a diverging second implementation with no scientific benefit.

Conventions
-----------
- Titles: ``>id`` or ``>id description``. ``id`` is the first whitespace-free
  token of the title; the remainder becomes ``description``.
- Sequence lines may be wrapped at any width; all non-whitespace characters
  after the title line are joined into a single sequence string.
- Records without any sequence characters produce an empty sequence, so
  degenerate files still round-trip through ``format_fasta``.
- Output: sequence lines are wrapped at 60 characters, the standard FASTA
  convention.

Assumptions
-----------
- Parsed FASTA records are typed as DNA (``SeqType.DNA``, the platform's
  default alphabet) and validated against it, so any sequence containing a
  character outside the DNA alphabet (in particular ``U``) is rejected at
  parse time. Callers dealing with RNA records should build
  ``SequenceRecord`` instances with ``seq_type=SeqType.RNA`` directly rather
  than routing RNA FASTA through the parser.
- Parsed records carry ``source_database=""``: the parser does not know
  which database a file came from, so the retrieval client that called it
  stamps the origin afterwards.
"""

from __future__ import annotations

import io
from collections.abc import Sequence

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqIO.FastaIO import FastaWriter
from Bio.SeqRecord import SeqRecord

from sequence_platform.models import SeqType, SequenceRecord
from sequence_platform.validation import validate_sequence

#: Standard FASTA sequence line width in characters.
FASTA_LINE_WIDTH = 60


def _split_title(title: str) -> tuple[str, str]:
    """Split a FASTA title line into ``(accession, description)``.

    The accession is the first whitespace-free token of the stripped title;
    the description is the remainder of the line, stripped of surrounding
    whitespace. A title with a single token, or an empty title, yields an
    empty description.
    """
    parts = title.strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1].strip()


def _header_for(record: SequenceRecord) -> str:
    """Build the FASTA title line (without ``>``) for one record.

    The line is the accession on its own when the record's description is
    empty, otherwise ``<accession> <description>``. When the description
    already starts with the accession, it is written as-is so the accession
    appears exactly once; otherwise the written line is derived from the
    accession and description so that output follows the ``>id description``
    convention.
    """
    description = record.description.strip()
    if not description:
        return record.accession
    if description.split(None, 1)[0] == record.accession:
        # The description already carries the accession as its first token
        # (the same dedup rule Biopython's FastaWriter applies); prepending
        # the accession again would duplicate it in the written title line.
        return description
    return f"{record.accession} {description}"


def format_fasta(
    records: Sequence[SequenceRecord],
    wrap: int = FASTA_LINE_WIDTH,
) -> str:
    """Format records as a single FASTA document.

    Args:
        records: The records to write, in the order they should appear in
            the document.
        wrap: Width (in characters) at which sequence lines are wrapped.
            Defaults to ``FASTA_LINE_WIDTH`` (60, the standard FASTA
            convention).

    Returns:
        The FASTA text. Each record contributes a title line (``>id`` or
        ``>id description``) followed by newline-terminated sequence lines;
        records with an empty sequence contribute a title line only. The
        document therefore ends with a trailing newline.
    """
    buffer = io.StringIO()
    writer = FastaWriter(buffer, wrap=wrap)
    for record in records:
        writer.write_record(
            SeqRecord(
                id=record.accession,
                description=_header_for(record),
                seq=Seq(record.sequence),
            )
        )
    return buffer.getvalue()


def parse_fasta(text: str) -> list[SequenceRecord]:
    """Parse a FASTA document into ``SequenceRecord`` instances.

    Args:
        text: The full FASTA document: any number of records, sequence
            lines wrapped at any width, LF or CRLF line endings.

    Returns:
        The records in file order. Each record's accession is the first
        token of its title line, its description is the remainder of the
        title, its title is the full title line, its seq_type is
        ``SeqType.DNA``, and its sequence is the upper-cased concatenation
        of all of its sequence lines (possibly empty for title-only
        records).

    Raises:
        ValueError: If a title line carries no accession token, or if a
            non-empty sequence contains characters outside the DNA
            alphabet.
    """
    if not text.strip():
        return []

    records: list[SequenceRecord] = []
    for index, seq_record in enumerate(
        SeqIO.parse(io.StringIO(text), "fasta"), start=1
    ):
        raw_title = seq_record.description
        title = raw_title.strip()
        accession, description = _split_title(title)
        if not accession:
            raise ValueError(
                f"FASTA record {index} has an empty accession (title line: {raw_title!r})"
            )
        raw_sequence = str(seq_record.seq)
        if raw_sequence:
            sequence = validate_sequence(raw_sequence)
        else:
            # Title-only record. validate_sequence rejects empty input, so
            # it is bypassed for these.
            sequence = ""
        records.append(
            SequenceRecord(
                accession=accession,
                sequence=sequence,
                seq_type=SeqType.DNA,
                title=title,
                description=description,
                source_database="",
                metadata={},
            )
        )
    return records
