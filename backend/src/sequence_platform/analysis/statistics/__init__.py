"""Sequence statistics (Stage 4).

Pure, deterministic functions: sequence length, GC content, base
composition, ambiguous-base content, and N-run metrics. No I/O, no
network, no ``database``/``api`` imports (§1 layering). See
``analysis.statistics.base`` for the documented rules.
"""

from sequence_platform.analysis.statistics.base import (
    ambiguous_base_count,
    ambiguous_base_percentage,
    base_composition,
    gc_content,
    longest_n_run,
    n_run_count,
    sequence_length,
)

__all__ = [
    "ambiguous_base_count",
    "ambiguous_base_percentage",
    "base_composition",
    "gc_content",
    "longest_n_run",
    "n_run_count",
    "sequence_length",
]
