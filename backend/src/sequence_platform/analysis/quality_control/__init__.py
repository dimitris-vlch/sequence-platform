"""Sequence quality-control metrics (Stage 4).

Threshold-based checks over the pure ``analysis.statistics`` functions;
``quality_report`` aggregates them into a ``QualityReport``. No I/O, no
network, no ``database``/``api`` imports (§1 layering).
"""

from sequence_platform.analysis.quality_control.base import (
    DEFAULT_MAX_AMBIGUOUS_FRACTION,
    DEFAULT_MAX_N_RUN,
    DEFAULT_MIN_LENGTH,
    QualityReport,
    quality_report,
)

__all__ = [
    "DEFAULT_MAX_AMBIGUOUS_FRACTION",
    "DEFAULT_MAX_N_RUN",
    "DEFAULT_MIN_LENGTH",
    "QualityReport",
    "quality_report",
]
