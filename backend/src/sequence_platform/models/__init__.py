"""Domain models for the sequence platform.

Nucleotide-only data structures shared by the database, analysis, and
API layers.
"""

from sequence_platform.models.base import SeqType, SequenceRecord

__all__ = [
    "SeqType",
    "SequenceRecord",
]
