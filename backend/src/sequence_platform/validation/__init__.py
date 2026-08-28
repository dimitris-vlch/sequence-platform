"""Sequence validation utilities.

Validation is the boundary at which untrusted text becomes a trusted
``SequenceRecord``: everything that touches raw external strings (database
responses, user uploads) should run through these checks before the data is
used by analysis code.
"""

from sequence_platform.validation.base import (
    SequenceValidationError,
    is_valid_sequence,
    validate_sequence,
)

__all__ = [
    "SequenceValidationError",
    "is_valid_sequence",
    "validate_sequence",
]
