"""NCBI sequence database client."""

from sequence_platform.database.ncbi.fasta import (
    FASTA_LINE_WIDTH,
    format_fasta,
    parse_fasta,
)
from sequence_platform.database.registry import SUPPORTED_DATABASES

__all__ = [
    "FASTA_LINE_WIDTH",
    "SUPPORTED_DATABASES",
    "format_fasta",
    "parse_fasta",
]
