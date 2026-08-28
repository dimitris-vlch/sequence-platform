"""Shared building blocks for analysis modules.

Modules in ``analysis/`` are pure functions over ``SequenceRecord``
objects (or plain strings) with no I/O, no network, and no global state.
This module holds the small shared helpers used by more than one module.
"""

from __future__ import annotations

from sequence_platform.models import SeqType, SequenceRecord

__all__ = [
    "SequenceRecord",
    "SeqType",
]
