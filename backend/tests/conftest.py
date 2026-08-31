"""Shared pytest fixtures for the backend test suite.

The shared hand-designed reference sequences used by known-answer tests
live here, not copy-pasted into individual test files.
"""

import pytest

from sequence_platform.models import SeqType, SequenceRecord


@pytest.fixture
def all_nucleotides() -> SequenceRecord:
    """A record covering all 15 IUPAC nucleotide codes, each exactly once.

    The four unambiguous bases (``ACGT``) plus the eleven ambiguity codes
    (``RYSWKMBDHVN``), in IUPAC table order.
    """
    return SequenceRecord(
        accession="NM_000001",
        sequence="ACGTRYSWKMBDHVN",
        seq_type=SeqType.DNA,
        title="NM_000001 all IUPAC nucleotide codes",
        description="all IUPAC nucleotide codes",
        source_database="",
        metadata={},
    )


@pytest.fixture
def ambiguous_reference() -> SequenceRecord:
    """A record whose sequence uses only IUPAC ambiguity codes.

    The eleven ambiguity codes (``RYSWKMBDHVN``) repeated twice; it
    contains no unambiguous bases.
    """
    return SequenceRecord(
        accession="R_1",
        sequence="RYSWKMBDHVN" * 2,
        seq_type=SeqType.DNA,
        title="R_1 reference assembled from ambiguity codes only",
        description="reference assembled from ambiguity codes only",
        source_database="",
        metadata={},
    )
