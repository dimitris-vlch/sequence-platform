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
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import Any

from Bio import FastaIO, SeqIO
from Bio.Seq import Seq

from sequence_platform.models import SequenceRecord
from sequence_platform.validation import validate_sequence