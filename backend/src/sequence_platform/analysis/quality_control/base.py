"""Threshold-based sequence quality checks (Stage 4).

Aggregates the pure :mod:`sequence_platform.analysis.statistics`
functions into a :class:`QualityReport`. No I/O, no network, no
``database`` or ``api`` imports (``docs/architecture.md`` §1 layering).

Semantics (``docs/architecture.md`` §6, Stage 4): every threshold
comparison is strict (``>`` / ``<``) — a record that exactly meets a
threshold passes that check. Defaults are overridable per call (and,
from the API layer, per request).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sequence_platform.analysis import statistics
from sequence_platform.analysis.statistics.base import SequenceLike
from sequence_platform.models import SeqType

__all__ = [
    "DEFAULT_MAX_AMBIGUOUS_FRACTION",
    "DEFAULT_MAX_N_RUN",
    "DEFAULT_MIN_LENGTH",
    "QualityReport",
    "quality_report",
]

#: Default thresholds applied by :func:`quality_report`.
DEFAULT_MIN_LENGTH = 100
DEFAULT_MAX_AMBIGUOUS_FRACTION = 0.10
DEFAULT_MAX_N_RUN = 10


@dataclass
class QualityReport:
    """Outcome of the QC battery for one record.

    ``passed`` is ``True`` only when no check failed; ``issues`` lists
    one human-readable message per failed check, in check order.
    """

    passed: bool
    issues: list[str] = field(default_factory=list)


def quality_report(
    record_or_sequence: SequenceLike,
    *,
    min_length: int = DEFAULT_MIN_LENGTH,
    max_ambiguous_fraction: float = DEFAULT_MAX_AMBIGUOUS_FRACTION,
    max_n_run: int = DEFAULT_MAX_N_RUN,
    seq_type: SeqType = SeqType.DNA,
) -> QualityReport:
    """Run the full QC battery and aggregate the outcome.

    Checks, in order (all strict ``>`` / ``<``):

    1. ``length < min_length``
    2. ``ambiguous fraction > max_ambiguous_fraction``
    3. ``longest N-run > max_n_run``
    """
    length = statistics.sequence_length(record_or_sequence, seq_type=seq_type)
    ambiguous_percentage = statistics.ambiguous_base_percentage(
        record_or_sequence, seq_type=seq_type
    )
    longest_n_run = statistics.longest_n_run(record_or_sequence, seq_type=seq_type)

    issues: list[str] = []
    if length < min_length:
        issues.append(f"length {length} is below the minimum {min_length}")
    if ambiguous_percentage > max_ambiguous_fraction * 100.0:
        issues.append(
            f"ambiguous fraction {ambiguous_percentage:.2f}% exceeds "
            f"the maximum {max_ambiguous_fraction * 100.0:.2f}%"
        )
    if longest_n_run > max_n_run:
        issues.append(f"longest N-run {longest_n_run} exceeds the maximum {max_n_run}")

    return QualityReport(passed=not issues, issues=issues)