"""Export serialisation: provenance blocks, FASTA documents, alignment text.

Stage 9. This module turns results the platform has already computed into
documents a user can download, and computes nothing biological:

- the FASTA document comes from ``SequenceRecord.to_fasta()``, the domain
  model's own entry point into the platform's single Biopython-backed FASTA
  writer (``database/ncbi/fasta.py``, ``FastaWriter``) — never a second,
  hand-rolled formatter;
- the pairwise-alignment text is a three-line EMBOSS-style display built from
  the two gapped strings, because ``analysis/alignment`` returns only those
  strings (the Biopython ``Alignment`` object is discarded), so Biopython's
  own ``str(alignment)`` display is not reachable from an API-layer result,
  and re-running the aligner here would mean computing rather than
  serialising;
- the only derived values are the §4 provenance facts (sequence MD5 digests,
  UTC timestamp) and the alignment match line.

Deliberately free of FastAPI imports: this is a plain, unit-testable
serialisation module. The routes in ``api/routes/exports.py`` own the HTTP
details (status codes, media types, download headers).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from datetime import UTC, datetime

from sequence_platform import __version__
from sequence_platform.models import SequenceRecord

from .schemas import AlignmentResponse, ExportProvenance, ExportSource

#: Application name recorded in every export's provenance block.
APPLICATION_NAME = "sequence-platform"

#: Gap character used in the gapped strings from ``analysis/alignment``.
GAP_CHARACTER = "-"
#: Match-line characters (``|`` match, ``.`` mismatch, space gap).
MATCH_CHARACTER = "|"
MISMATCH_CHARACTER = "."
GAP_MARKER = " "

#: Everything allowed in a download filename. ASCII only (HTTP header values
#: are latin-1 encoded) and no path separators or quotes — accessions are
#: user input and end up inside ``Content-Disposition``.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def sequence_md5(sequence: str) -> str:
    """Hex MD5 digest of a sequence, as required by §4 for provenance."""
    return hashlib.md5(sequence.encode("utf-8"), usedforsecurity=False).hexdigest()


def safe_filename(stem: str, suffix: str) -> str:
    """Build a download filename that is safe for an HTTP header.

    Anything outside ``[A-Za-z0-9._-]`` becomes ``_``; leading/trailing dots
    and underscores are dropped, and an empty stem falls back to ``export``.
    """
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", stem).strip("._")
    return f"{cleaned or 'export'}{suffix}"


def content_disposition(filename: str) -> str:
    """The ``Content-Disposition`` value that makes a browser download."""
    return f'attachment; filename="{filename}"'


def provenance(
    records: Sequence[SequenceRecord],
    *,
    parameters: dict[str, object] | None = None,
) -> ExportProvenance:
    """Build the §4 provenance block for an export of ``records``.

    One ``ExportSource`` per input record, in the order the records were
    used, followed by the analysis parameters the result was computed with.
    """
    return ExportProvenance(
        generated_at=datetime.now(UTC).isoformat(),
        application=APPLICATION_NAME,
        version=__version__,
        sources=[
            ExportSource(
                accession=record.accession,
                source_database=record.source_database,
                length=record.length,
                md5=sequence_md5(record.sequence),
                metadata=dict(record.metadata),
            )
            for record in records
        ],
        parameters=dict(parameters or {}),
    )


def match_line(aligned_a: str, aligned_b: str) -> str:
    """EMBOSS-style match line for two gapped strings.

    ``|`` for a match, ``.`` for a mismatch, and a space where either side is
    a gap. Iterates to the longer of the two strings, so a length
    disagreement (which the alignment layer does not produce, but which this
    formatter does not assume) cannot silently drop columns.
    """
    width = max(len(aligned_a), len(aligned_b))
    characters: list[str] = []
    for index in range(width):
        a = aligned_a[index] if index < len(aligned_a) else GAP_CHARACTER
        b = aligned_b[index] if index < len(aligned_b) else GAP_CHARACTER
        if a == GAP_CHARACTER or b == GAP_CHARACTER:
            characters.append(GAP_MARKER)
        elif a == b:
            characters.append(MATCH_CHARACTER)
        else:
            characters.append(MISMATCH_CHARACTER)
    return "".join(characters)


def alignment_text(response: AlignmentResponse) -> str:
    """Human-readable pairwise alignment: both sequences plus a match line.

    The label column is padded to the longer accession, and the full aligned
    strings are written — truncation is a display concern, not an export one.
    """
    line = match_line(response.aligned_a, response.aligned_b)
    width = max(len(response.accession_a), len(response.accession_b))
    header = [
        "# sequence-platform pairwise alignment export",
        f"# mode: {response.mode}, score: {response.score}",
        f"# columns: {len(line)} (matches {line.count(MATCH_CHARACTER)}, "
        f"mismatches {line.count(MISMATCH_CHARACTER)}, gaps {line.count(GAP_MARKER)})",
        "# match line: | match, . mismatch, space gap",
        "",
    ]
    rows = [
        f"{response.accession_a:<{width}} {response.aligned_a}",
        f"{'':<{width}} {line}",
        f"{response.accession_b:<{width}} {response.aligned_b}",
        "",
    ]
    return "\n".join(header + rows)
