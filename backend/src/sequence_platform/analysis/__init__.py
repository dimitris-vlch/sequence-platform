"""Sequence analysis layer.

Pure, deterministic functions operating on ``SequenceRecord``/``str``
inputs. This layer never touches the network, the ``database`` package,
or any ``api`` object (§1 layering): a result is a pure function of the
record it is given, so it is reproducible offline.

Subpackages: ``core`` (intentionally empty stub — see
``docs/architecture.md`` §6 Stage 4), ``statistics`` and
``quality_control`` (Stage 4), ``distance`` and ``similarity`` (Stage 5),
``alignment`` (Stage 6).
"""

from . import alignment, distance, quality_control, similarity, statistics

__all__ = ["alignment", "distance", "quality_control", "similarity", "statistics"]
