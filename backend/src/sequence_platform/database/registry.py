"""Database client registry.

Maps provider names (``"ncbi"``, ``"ena"``, ...) to their
:class:`SequenceDatabase` implementations.

Two lists live here, and they are deliberately different:

- ``SUPPORTED_DATABASES`` — every archive the platform is designed to
  support, in display order. Advertised by the API even when no client is
  implemented for it yet (surfaced with ``available: false``).
- ``_FACTORIES`` — the subset with a working client. Currently just NCBI
  (Stage 3); ENA joins in Stage 7.

``get_database`` constructs clients lazily: one fresh client per call,
configured from the current environment (``Settings``), so callers own the
lifecycle. The app factory (``main.create_app``) additionally holds one
long-lived client per provider for the process lifetime.
"""

from __future__ import annotations

from collections.abc import Callable

from sequence_platform.config import Settings, get_settings
from sequence_platform.database.base import SequenceDatabase
from sequence_platform.database.exceptions import UnknownDatabaseError

__all__ = ["SUPPORTED_DATABASES", "get_database", "registered_names"]

# Databases planned for the first release, in display order.
SUPPORTED_DATABASES: tuple[str, ...] = ("ncbi", "ena")


def _ncbi_factory(settings: Settings) -> SequenceDatabase:
    """Construct the NCBI client from ``settings``."""
    # Imported here (not at module level) to avoid an import cycle:
    # ``ncbi/__init__.py`` re-exports from this module. Importing the
    # submodule directly bypasses the package's ``__init__``.
    from sequence_platform.database.ncbi.client import NCBISequenceDatabase

    return NCBISequenceDatabase(settings=settings)


# Provider name -> one-argument (Settings) client factory.
_FACTORIES: dict[str, Callable[[Settings], SequenceDatabase]] = {
    "ncbi": _ncbi_factory,
}


def registered_names() -> tuple[str, ...]:
    """Names of providers with an implemented client, in registration order."""
    return tuple(_FACTORIES)


def get_database(name: str, settings: Settings | None = None) -> SequenceDatabase:
    """Return a freshly constructed client for the named provider.

    Args:
        name: Provider name as registered (``"ncbi"``).
        settings: Optional explicit settings; when omitted, the current
            environment is read at call time (see
            :func:`sequence_platform.config.get_settings`).

    Raises:
        UnknownDatabaseError: If no client is registered under ``name``
            (e.g. ``"ena"`` until Stage 7); the API layer maps this to 404.
    """
    factory = _FACTORIES.get(name)
    if factory is None:
        available = ", ".join(registered_names())
        raise UnknownDatabaseError(
            f"No client registered for database {name!r}; registered: {available}"
        )
    return factory(settings if settings is not None else get_settings())
