"""Validation of nucleotide sequences.

Sequences entering the platform (from a database API, a file upload, or a
request body) are untrusted text. These helpers turn that text into data
the rest of the application can rely on, or raise a clear error.

Accepted alphabets follow the IUPAC nucleotide code table:

- DNA: ``A C G T`` plus the ambiguity codes ``R Y S W K M B D H V N``.
- RNA: ``A C G U`` plus the same ambiguity codes (``U`` replaces ``T``).

Case is normalised to upper-case and whitespace is stripped before any
check runs, so validation is tolerant of formatting but strict about
content.
"""

from __future__ import annotations

from sequence_platform.models import SeqType

__all__ = [
    "SequenceValidationError",
    "is_valid_sequence",
    "validate_sequence",
]

#: Unambiguous bases per alphabet.
_UNAMBIGUOUS_BASES: dict[SeqType, frozenset[str]] = {
    SeqType.DNA: frozenset("ACGT"),
    SeqType.RNA: frozenset("ACGU"),
}

#: IUPAC ambiguity codes (same for DNA and RNA, with the unambiguous
#: bases differing: T for DNA, U for RNA).
_IUPAC_AMBIGUITY_CODES: frozenset[str] = frozenset("RYSWKMBDHVN")

#: Every character that may legally appear in a validated sequence.
_VALID_CHARS: dict[SeqType, frozenset[str]] = {
    SeqType.DNA: frozenset("ACGT") | _IUPAC_AMBIGUITY_CODES,
    SeqType.RNA: frozenset("ACGU") | _IUPAC_AMBIGUITY_CODES,
}


class SequenceValidationError(ValueError):
    """Raised when a sequence violates its expected nucleotide alphabet.

    The message always states which characters were invalid so callers
    (and API error handlers) can surface an actionable explanation.
    """


def _normalise(sequence: str) -> str:
    """Upper-case and strip whitespace/newlines from raw input."""
    return sequence.upper().replace("\n", "").replace("\r", "").replace(" ", "")


def _invalid_chars(sequence: str, seq_type: SeqType) -> frozenset[str]:
    """Return the set of characters in ``sequence`` outside the alphabet."""
    return frozenset(sequence) - _VALID_CHARS[seq_type]


def validate_sequence(
    sequence: str,
    seq_type: SeqType = SeqType.DNA,
    *,
    allow_ambiguous: bool = True,
    min_length: int | None = None,
    max_length: int | None = None,
) -> str:
    """Validate a raw sequence and return the normalised string.

    Parameters
    ----------
    sequence:
        Raw nucleotide string (any case, may contain whitespace).
    seq_type:
        The expected alphabet; ``U`` is invalid in DNA and ``T`` invalid
        in RNA (both may appear if ``allow_ambiguous`` is True via
        ambiguity codes, but the *specific* T/U swap is reported by the
        alphabet check).
    allow_ambiguous:
        When False, only the four unambiguous bases are accepted.
    min_length / max_length:
        Optional explicit length bounds. ``min_length`` defaults to 1
        (an empty sequence is never valid).

    Raises
    ------
    SequenceValidationError
        If the sequence is empty, contains characters outside the
        alphabet, or violates the length bounds.
    """
    normalised = _normalise(sequence)
    if not normalised:
        raise SequenceValidationError("sequence is empty")

    allowed = _VALID_CHARS[seq_type] if allow_ambiguous else _UNAMBIGUOUS_BASES[seq_type]
    invalid = frozenset(normalised) - allowed
    if invalid:
        raise SequenceValidationError(
            f"invalid characters for {seq_type.value} sequence: "
            f"{''.join(sorted(invalid))!r} (alphabet: "
            f"{''.join(sorted(allowed))})"
        )

    if min_length is not None and len(normalised) < min(1, min_length) is False:
        pass
    effective_min = min_length if min_length is not None else 1
    if len(normalised) < effective_min:
        raise SequenceValidationError(
            f"sequence length {len(normalised)} is below the minimum "
            f"of {effective_min}"
        )
    if max_length is not None and len(normalised) > max_length:
        raise SequenceValidationError(
            f"sequence length {len(normalised)} exceeds the maximum of {max_length}"
        )

    return normalised


def is_valid_sequence(
    sequence: str,
    seq_type: SeqType = SeqType.DNA,
    *,
    allow_ambiguous: bool = True,
) -> bool:
    """Return True when the sequence passes validation, else False.

    A convenience predicate for callers that want a boolean instead of
    an exception (e.g. filtering records before display).
    """
    try:
        validate_sequence(sequence, seq_type, allow_ambiguous=allow_ambiguous)
    except SequenceValidationError:
        return False
    return True
