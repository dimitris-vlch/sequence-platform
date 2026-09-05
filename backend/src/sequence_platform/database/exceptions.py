"""Typed exception hierarchy for the database layer.

Per the architecture notes (§2 external-service policy) the database layer
raises *only* these types, and only after all retryable failures have
exhausted their retries. The API layer maps them onto HTTP status codes
(404 unknown accession, 422 malformed payload, 429 rate limited, 503
upstream down); the mapping itself lives in ``api/`` so that this module
stays HTTP-agnostic (§1 layering).
"""

from __future__ import annotations

__all__ = [
    "AccessionNotFoundError",
    "DatabaseError",
    "MalformedPayloadError",
    "RateLimitedError",
    "UpstreamUnavailableError",
    "UnknownDatabaseError",
]


class DatabaseError(Exception):
    """Base class for every error the database layer can raise."""


class AccessionNotFoundError(DatabaseError):
    """The upstream archive holds no record for the requested accession."""


class UnknownDatabaseError(DatabaseError):
    """The requested provider name has no registered client."""


class MalformedPayloadError(DatabaseError):
    """The upstream responded, but the payload is unusable.

    Covers unparseable documents, documents with the wrong number of
    records, and sequence content that fails validation against its
    alphabet.
    """


class RateLimitedError(DatabaseError):
    """The upstream kept rate-limiting after every retry was spent.

    Attributes:
        retry_after: The last ``Retry-After`` value the upstream sent, in
            seconds, or ``None`` when the response carried none. Surfaced
            by the API layer as the ``Retry-After`` response header.
    """

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class UpstreamUnavailableError(DatabaseError):
    """The upstream is unreachable or rejected the request.

    Covers 5xx responses, timeouts, and network failures after all retries
    were spent, plus non-429 client errors (including NCBI's quirk of
    answering unknown accessions with HTTP 400).
    """
