"""Provider-neutral sequence database interface.

Every external archive client (NCBI in Stage 3, ENA in Stage 7, ...)
implements `SequenceDatabase` and converts provider-specific responses into
the neutral domain model (`sequence_platform.models`). The analysis layer
and the API layer depend only on this interface, never on a concrete
provider client, so adding a new archive requires no changes elsewhere.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from sequence_platform.models import SequenceRecord

__all__ = [
    "SequenceDatabase",
    "SequenceSummary",
]


@dataclass
class SequenceSummary:
    """A lightweight card for one search hit.

    This is a database-layer type: enough for the API layer to render a
    result list (and the UI to show it), without the full sequence. A
    follow-up `fetch` yields the complete `SequenceRecord`.

    Attributes:
        accession: Provider accession (versioned when the provider says so).
        title: Short display title, as reported by the provider.
        length: Sequence length in nucleotides, or ``None`` when the
            provider did not report one.
        source_database: Provider name (e.g. ``"ncbi"``).
        metadata: Raw provider fields, preserved for provenance fidelity;
            missing values are kept as ``None`` rather than dropped.
    """

    accession: str
    title: str = ""
    length: int | None = None
    source_database: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class SequenceDatabase(ABC):
    """The contract every sequence database client implements.

    All methods are async: clients perform network I/O, and the platform
    is a single async FastAPI service. Implementations raise the typed
    exceptions from `sequence_platform.database.exceptions` (never raw
    ``httpx`` errors); the API layer maps those onto HTTP status codes.
    """

    #: Registry key / provider name (e.g. ``"ncbi"``).
    name: ClassVar[str]

    @abstractmethod
    async def fetch(self, accession: str) -> SequenceRecord:
        """Fetch one complete record for ``accession``.

        Raises:
            AccessionNotFoundError: The archive holds no such record.
            MalformedPayloadError: The upstream payload is unusable.
            RateLimitedError: The upstream is still rate-limiting after
                every retry was spent.
            UpstreamUnavailableError: The upstream is down or rejected the
                request after every retry was spent.
        """

    @abstractmethod
    async def search(
        self, query: str, *, max_results: int = 20
    ) -> list[SequenceSummary]:
        """Run a free-text search, returning at most ``max_results`` hits.

        An empty hit list is a normal result (surfaced as 200 with an
        empty list by the API layer), not an error.
        """

    async def close(self) -> None:
        """Release the client's resources (connection pool).

        The default is a no-op; implementations that hold a client must
        override this. Called once at application shutdown.
        """
