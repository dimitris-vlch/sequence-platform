"""Core domain models for nucleotide sequences.

The platform is strictly nucleotide-only (DNA and RNA). These models are
plain dataclasses, independent of any database or analysis layer, so every
part of the application can exchange sequence data without coupling.

``SequenceRecord`` is the single canonical in-memory representation of a
nucleotide sequence. Database clients produce it, analysis functions
consume it, and API routes serialise it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SeqType(str, Enum):
    """Nucleotide alphabet expected by the sequence.

    The alphabet matters for validation and for metrics that behave
    differently on DNA versus RNA (for example GC content reporting).
    """

    DNA = "dna"
    RNA = "rna"


#: Unambiguous bases for each alphabet.
_UNAMBIGUOUS_BASES: dict[SeqType, frozenset[str]] = {
    SeqType.DNA: frozenset("ACGT"),
    SeqType.RNA: frozenset("ACGU"),
}

#: IUPAC nucleotide ambiguity codes (identical for DNA and RNA). Must match
#: ``sequence_platform.validation.base._IUPAC_AMBIGUITY_CODES``; ``H`` and
#: ``V`` were previously missing here, so ``valid_bases`` disagreed with the
#: validator about which sequences are legal.
_AMBIGUITY_CODES: frozenset[str] = frozenset("RYSWKMBDHVN")


@dataclass
class SequenceRecord:
    """A single nucleotide sequence with provenance.

    Attributes
    ----------
    accession:
        Database accession or locally generated identifier.
    sequence:
        The nucleotide string, upper-case, no whitespace.
    seq_type:
        Expected alphabet. Defaults to DNA; RNA is used for
        transcript/coding-sequence records.
    title:
        Short display title (e.g. ``"seq1"`` for a FASTA title).
    description:
        Optional longer description text.
    source_database:
        Origin database (``"ncbi"``, ``"ena"``, ``"local"`` ...).
    metadata:
        Free-form provenance/metadata, preserved as-is. Records coming
        from an API keep their raw fields here so nothing is silently
        dropped; the application treats missing keys as absent rather
        than fabricating values.
    """

    accession: str
    sequence: str
    seq_type: SeqType = SeqType.DNA
    title: str = ""
    description: str = ""
    source_database: str = "local"
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalise: upper-case, strip whitespace. Sequences are always
        # stored in canonical form so downstream code never has to worry
        # about case.
        # ``"".join(s.split())`` drops every kind of whitespace (CR from CRLF
        # input, tabs), not only LF and spaces.
        self.sequence = "".join(self.sequence.upper().split())
        if not self.title:
            self.title = self.accession

    @property
    def length(self) -> int:
        """Sequence length in nucleotides."""
        return len(self.sequence)

    @property
    def valid_bases(self) -> frozenset[str]:
        """Bases accepted for this sequence type, including ambiguity."""
        return _UNAMBIGUOUS_BASES[self.seq_type] | _AMBIGUITY_CODES

    def to_fasta(self, wrap: int = 60) -> str:
        """Render this record as a single-record FASTA string.

        The full formatting rules live in ``sequence_platform.database.ncbi.fasta``;
        this convenience method delegates to it so the rules are defined
        exactly once.
        """
        from sequence_platform.database.ncbi.fasta import format_fasta

        return format_fasta([self], wrap=wrap)
