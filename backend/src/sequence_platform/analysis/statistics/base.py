"""Pure sequence-statistics helpers (Stage 4).

Every function is deterministic and side-effect free: no I/O, no
network, no ``database`` or ``api`` imports (``docs/architecture.md``
§1 layering). Inputs accept either a
:class:`sequence_platform.models.SequenceRecord` or a plain string, so
the same math applies to fetched records and to locally supplied text.

Documented rules (``docs/architecture.md`` §6, Stage 4):

- Case is normalised to upper-case once, before any computation.
- "Standard bases" are the unambiguous letters of the record's alphabet
  (``ACGT`` for DNA, ``ACGU`` for RNA); ``N`` and the IUPAC ambiguity
  codes ``RYSWKMBDHVN`` count as *ambiguous*.
- ``gc_content`` is relative to standard bases only and is ``None`` when
  the sequence has none; all other percentages are relative to the full
  sequence length.
- N-runs are runs of consecutive ``N`` characters only; the other
  ambiguity codes do not form N-runs.
- Characters outside the IUPAC table (e.g. ``X``) are ignored by every
  metric; they are a validation concern, not a statistics one.
"""

from __future__ import annotations

from sequence_platform.models import SeqType, SequenceRecord
from sequence_platform.validation.base import (
    _IUPAC_AMBIGUITY_CODES,
    _UNAMBIGUOUS_BASES,
)

__all__ = [
    "SequenceLike",
    "ambiguous_base_count",
    "ambiguous_base_percentage",
    "base_composition",
    "gc_content",
    "longest_n_run",
    "n_run_count",
    "sequence_length",
]

SequenceLike = SequenceRecord | str

#: Composition keys per alphabet, in a stable order.
_COMPOSITION_STANDARD: dict[SeqType, tuple[str, ...]] = {
    SeqType.DNA: ("A", "C", "G", "T"),
    SeqType.RNA: ("A", "C", "G", "U"),
}

_AMBIGUOUS_KEY = "ambiguous"


def _normalised(
    record_or_sequence: SequenceLike, seq_type: SeqType
) -> tuple[str, SeqType]:
    """Upper-case the sequence once and pin its alphabet.

    For records the record's own ``seq_type`` wins; the ``seq_type``
    argument only applies to plain strings.
    """
    if isinstance(record_or_sequence, SequenceRecord):
        return str(record_or_sequence.sequence).upper(), record_or_sequence.seq_type
    return record_or_sequence.upper(), seq_type


def _percent(count: int, length: int) -> float:
    """``count`` as a percent of ``length``, rounded to two decimals."""
    if length == 0:
        return 0.0
    return round(100.0 * count / length, 2)


def sequence_length(
    record_or_sequence: SequenceLike, *, seq_type: SeqType = SeqType.DNA
) -> int:
    """Length in bases."""
    sequence, _ = _normalised(record_or_sequence, seq_type)
    return len(sequence)


def gc_content(
    record_or_sequence: SequenceLike, *, seq_type: SeqType = SeqType.DNA
) -> float | None:
    """GC content in percent, relative to standard bases only.

    Returns ``None`` when the sequence contains no standard bases.
    """
    sequence, effective_seq_type = _normalised(record_or_sequence, seq_type)
    standard = _UNAMBIGUOUS_BASES[effective_seq_type]
    standard_count = sum(1 for base in sequence if base in standard)
    if standard_count == 0:
        return None
    gc_count = sum(1 for base in sequence if base in ("G", "C"))
    return round(100.0 * gc_count / standard_count, 2)


def base_composition(
    record_or_sequence: SequenceLike, *, seq_type: SeqType = SeqType.DNA
) -> dict[str, float]:
    """Base composition in percent of the full sequence length.

    Keys are the standard bases of the record's alphabet plus a single
    ``"ambiguous"`` bucket (``N`` + the IUPAC ambiguity codes).
    """
    sequence, effective_seq_type = _normalised(record_or_sequence, seq_type)
    length = len(sequence)
    result: dict[str, float] = {
        base: _percent(sequence.count(base), length)
        for base in _COMPOSITION_STANDARD[effective_seq_type]
    }
    result[_AMBIGUOUS_KEY] = _percent(
        sum(1 for char in sequence if char in _IUPAC_AMBIGUITY_CODES), length
    )
    return result


def ambiguous_base_count(
    record_or_sequence: SequenceLike, *, seq_type: SeqType = SeqType.DNA
) -> int:
    """Count of ``N`` and the IUPAC ambiguity codes (``RYSWKMBDHVN``)."""
    sequence, _ = _normalised(record_or_sequence, seq_type)
    return sum(1 for char in sequence if char in _IUPAC_AMBIGUITY_CODES)


def ambiguous_base_percentage(
    record_or_sequence: SequenceLike, *, seq_type: SeqType = SeqType.DNA
) -> float:
    """Ambiguous bases as a percent of the full length (0.0 if empty)."""
    sequence, _ = _normalised(record_or_sequence, seq_type)
    return _percent(ambiguous_base_count(sequence), len(sequence))


def n_run_count(
    record_or_sequence: SequenceLike, *, seq_type: SeqType = SeqType.DNA
) -> int:
    """Number of runs of consecutive ``N`` characters.

    The other IUPAC ambiguity codes do not form N-runs.
    """
    sequence, _ = _normalised(record_or_sequence, seq_type)
    return sum(
        1
        for index, char in enumerate(sequence)
        if char == "N" and (index == 0 or sequence[index - 1] != "N")
    )


def longest_n_run(
    record_or_sequence: SequenceLike, *, seq_type: SeqType = SeqType.DNA
) -> int:
    """Length of the longest run of consecutive ``N`` characters."""
    sequence, _ = _normalised(record_or_sequence, seq_type)
    longest = 0
    current = 0
    for char in sequence:
        if char == "N":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest
