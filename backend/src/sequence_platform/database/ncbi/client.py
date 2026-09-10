"""Live NCBI E-utilities client.

``NCBISequenceDatabase`` is the only implementation of
``sequence_platform.database.base.SequenceDatabase`` backed by a real
external archive so far. It talks to NCBI's E-utilities
(https://eutils.ncbi.nlm.nih.gov/entrez/eutils/) over plain ``httpx``;
``Bio.Entrez`` is not used for I/O so that every request, retry, and error
path stays visible and testable through an injected ``httpx`` transport.
Biopython is used only downstream, to parse the FASTA payload
(``sequence_platform.database.ncbi.fasta.parse_fasta``).

Request flow for :meth:`NCBISequenceDatabase.fetch`:

1. ``esearch`` resolves the accession to a UID and confirms it exists
   (``count == 0`` -> :class:`AccessionNotFoundError`).
2. ``esummary`` fetches optional descriptive metadata for that UID. A
   failure here is not fatal to the fetch: the raw JSON is preserved under
   ``metadata["ncbi_esummary"]`` when available, otherwise metadata is
   left empty.
3. ``efetch`` retrieves the FASTA payload (``rettype=fasta,
   retmode=text``), which is parsed with
   ``parse_fasta(text, infer_seq_type=True)``.

:meth:`NCBISequenceDatabase.search` only calls ``esearch`` + ``esummary``
and returns lightweight ``SequenceSummary`` cards; it never calls
``efetch``.

Retry policy (kept together here as one deliberate policy, not scattered
per-call): 5xx responses, timeouts, and network errors are retried up to
``max_retries`` times with exponential backoff (``backoff_base`` seconds,
doubling, capped at ``backoff_cap``) plus jitter, then raise
``UpstreamUnavailableError``. HTTP 429 responses are retried the same way
but honour the upstream ``Retry-After`` header (capped at ``backoff_cap``
so a hostile header cannot stall the client indefinitely); once retries
are exhausted this raises ``RateLimitedError`` instead. Any other 4xx
response (including NCBI's habit of answering unknown accessions with a
plain HTTP 400 on some endpoints) is not retried and raises
``UpstreamUnavailableError`` immediately, since the accession was already
confirmed to exist by the preceding ``esearch`` call.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, ClassVar

import httpx

from sequence_platform.config import Settings
from sequence_platform.database.base import SequenceDatabase, SequenceSummary
from sequence_platform.database.exceptions import (
    AccessionNotFoundError,
    MalformedPayloadError,
    RateLimitedError,
    UpstreamUnavailableError,
)
from sequence_platform.database.ncbi.fasta import parse_fasta
from sequence_platform.models import SequenceRecord

__all__ = ["NCBISequenceDatabase"]

_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

#: Retry decisions and terminal failures are logged (Stage 10) so a deployment
#: can tell a transient upstream blip from a sustained outage. Logging only —
#: no branch below changes what the client retries or returns.
logger = logging.getLogger(__name__)


class NCBISequenceDatabase(SequenceDatabase):
    """``SequenceDatabase`` backed by the live NCBI E-utilities API."""

    name: ClassVar[str] = "ncbi"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        email: str | None = None,
        api_key: str | None = None,
        db: str = "nucleotide",
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        backoff_cap: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Build the client, optionally from ``settings``.

        Args:
            settings: Source for ``email``/``api_key`` when those are not
                given explicitly. Ignored for a field once that field's
                explicit keyword argument is provided.
            email: NCBI-recommended contact email, sent as ``email`` on
                every request. Falls back to ``settings.ncbi_email``.
            api_key: Optional NCBI API key, sent as ``api_key`` when set;
                raises NCBI's request-rate ceiling. Falls back to
                ``settings.ncbi_api_key``.
            db: E-utilities database segment (``"nucleotide"``).
            timeout: Per-request timeout in seconds.
            max_retries: Maximum retry attempts for retryable failures
                (429, 5xx, timeouts, network errors) before giving up.
            backoff_base: Initial backoff delay in seconds; doubles with
                each retry.
            backoff_cap: Maximum backoff delay in seconds, also used to
                cap a hostile/huge ``Retry-After`` header.
            transport: Optional ``httpx`` transport, used by tests to
                replace the network with a scripted mock transport.
        """
        self._email = (
            email if email is not None else (settings.ncbi_email if settings else None)
        )
        self._api_key = (
            api_key
            if api_key is not None
            else (settings.ncbi_api_key if settings else None)
        )
        self._db = db
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._client = httpx.AsyncClient(
            base_url=_EUTILS_BASE, timeout=timeout, transport=transport
        )

    async def close(self) -> None:
        """Close the underlying ``httpx`` connection pool."""
        await self._client.aclose()

    def _common_params(self) -> dict[str, str]:
        """Parameters NCBI expects on every E-utilities request."""
        params: dict[str, str] = {"tool": "sequence-platform"}
        if self._email:
            params["email"] = self._email
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    async def _request(self, path: str, params: dict[str, str]) -> httpx.Response:
        """GET ``path`` with the shared retry policy applied.

        Raises:
            RateLimitedError: 429 responses persisted through every retry.
            UpstreamUnavailableError: Any other failure (5xx, timeout,
                network error, or non-429 4xx) persisted through every
                retry, or was a non-429 4xx (never retried).
        """
        attempt = 0
        while True:
            try:
                response = await self._client.get(path, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self._max_retries:
                    logger.error(
                        "NCBI %s failed after %d retries: %s",
                        path,
                        self._max_retries,
                        exc,
                    )
                    raise UpstreamUnavailableError(
                        f"NCBI request to {path} failed after "
                        f"{self._max_retries} retries: {exc}"
                    ) from exc
                logger.warning(
                    "NCBI %s failed (%s); retrying (%d/%d)",
                    path,
                    exc,
                    attempt + 1,
                    self._max_retries,
                )
                await self._sleep_backoff(attempt)
                attempt += 1
                continue

            if response.status_code == 429:
                retry_after = self._parse_retry_after(response)
                if attempt >= self._max_retries:
                    logger.error(
                        "NCBI %s was rate-limited through all %d retries "
                        "(last Retry-After=%s)",
                        path,
                        self._max_retries,
                        retry_after,
                    )
                    raise RateLimitedError(
                        f"NCBI rate-limited requests to {path} after "
                        f"{self._max_retries} retries",
                        retry_after=retry_after,
                    )
                logger.warning(
                    "NCBI %s rate-limited (429, Retry-After=%s); retrying (%d/%d)",
                    path,
                    retry_after,
                    attempt + 1,
                    self._max_retries,
                )
                await self._sleep_backoff(attempt, retry_after=retry_after)
                attempt += 1
                continue

            if response.status_code >= 500:
                if attempt >= self._max_retries:
                    logger.error(
                        "NCBI %s returned %d through all %d retries",
                        path,
                        response.status_code,
                        self._max_retries,
                    )
                    raise UpstreamUnavailableError(
                        f"NCBI returned {response.status_code} for {path} "
                        f"after {self._max_retries} retries"
                    )
                logger.warning(
                    "NCBI %s returned %d; retrying (%d/%d)",
                    path,
                    response.status_code,
                    attempt + 1,
                    self._max_retries,
                )
                await self._sleep_backoff(attempt)
                attempt += 1
                continue

            if response.status_code >= 400:
                # Non-429 4xx: never retried. Covers NCBI's quirk of
                # answering some malformed/unknown requests with a plain
                # HTTP 400 on efetch/esummary.
                logger.error(
                    "NCBI %s returned %d (not retried)", path, response.status_code
                )
                raise UpstreamUnavailableError(
                    f"NCBI returned {response.status_code} for {path}"
                )

            return response

    async def _sleep_backoff(
        self, attempt: int, *, retry_after: float | None = None
    ) -> None:
        """Sleep before the next retry attempt.

        Honours an upstream ``Retry-After`` value (capped at
        ``backoff_cap``) when given; otherwise applies exponential backoff
        with jitter, doubling ``backoff_base`` per attempt and capping at
        ``backoff_cap``.
        """
        if retry_after is not None:
            delay = min(retry_after, self._backoff_cap)
        else:
            delay = min(self._backoff_base * (2**attempt), self._backoff_cap)
            delay *= random.uniform(0.5, 1.5)
        await asyncio.sleep(delay)

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        """Extract the ``Retry-After`` header value in seconds, if present."""
        header = response.headers.get("Retry-After")
        if header is None:
            return None
        try:
            return float(header)
        except ValueError:
            return None

    async def _esearch(self, accession: str) -> str:
        """Resolve ``accession`` to a UID via ``esearch``.

        Raises:
            AccessionNotFoundError: NCBI reports zero matches.
            MalformedPayloadError: The response is not the expected JSON
                shape.
        """
        params = {
            **self._common_params(),
            "db": self._db,
            "term": accession,
            "retmode": "json",
        }
        response = await self._request("esearch.fcgi", params)
        try:
            payload = response.json()
            result = payload["esearchresult"]
            id_list: list[str] = result["idlist"]
            count = int(result["count"])
        except (KeyError, ValueError, TypeError) as exc:
            raise MalformedPayloadError(
                f"NCBI esearch response for {accession!r} was not the "
                f"expected JSON shape: {exc}"
            ) from exc
        if count == 0 or not id_list:
            raise AccessionNotFoundError(
                f"NCBI has no {self._db} record for accession {accession!r}"
            )
        return id_list[0]

    async def _esummary(self, uid: str) -> dict[str, object]:
        """Fetch optional descriptive metadata for ``uid`` via ``esummary``.

        Never raises: a failure to obtain or parse the summary is not
        fatal to a fetch/search, so this returns ``{}`` on any problem and
        the raw entry (wrapped as ``{"ncbi_esummary": entry}``) otherwise.
        """
        params = {
            **self._common_params(),
            "db": self._db,
            "id": uid,
            "retmode": "json",
        }
        try:
            response = await self._request("esummary.fcgi", params)
            payload = response.json()
            entry = payload["result"][uid]
        except Exception:
            return {}
        return {"ncbi_esummary": entry}

    async def fetch(self, accession: str) -> SequenceRecord:
        """Fetch one complete record for ``accession`` from NCBI.

        Raises:
            AccessionNotFoundError: NCBI holds no record for ``accession``.
            MalformedPayloadError: The upstream payload is unusable (wrong
                shape, wrong record count, or invalid sequence content).
            RateLimitedError: NCBI kept rate-limiting after every retry.
            UpstreamUnavailableError: NCBI is down or rejected the request
                after every retry.
        """
        uid = await self._esearch(accession)
        metadata = await self._esummary(uid)

        efetch_params = {
            **self._common_params(),
            "db": self._db,
            "id": uid,
            "rettype": "fasta",
            "retmode": "text",
        }
        response = await self._request("efetch.fcgi", efetch_params)
        try:
            records = parse_fasta(response.text, infer_seq_type=True)
        except ValueError as exc:
            raise MalformedPayloadError(
                f"NCBI efetch FASTA for {accession!r} failed to parse: {exc}"
            ) from exc

        if not records:
            raise AccessionNotFoundError(
                f"NCBI efetch returned no FASTA record for accession {accession!r}"
            )
        if len(records) != 1:
            raise MalformedPayloadError(
                f"NCBI efetch returned {len(records)} FASTA records for "
                f"accession {accession!r}; expected exactly 1"
            )

        record = records[0]
        record.source_database = "ncbi"
        record.metadata = metadata
        return record

    async def search(
        self, query: str, *, max_results: int = 20
    ) -> list[SequenceSummary]:
        """Run a free-text search against NCBI, returning summary cards.

        An empty hit list is a normal result, not an error.

        Raises:
            MalformedPayloadError: A response was not the expected JSON
                shape.
            RateLimitedError: NCBI kept rate-limiting after every retry.
            UpstreamUnavailableError: NCBI is down or rejected the request
                after every retry.
        """
        search_params = {
            **self._common_params(),
            "db": self._db,
            "term": query,
            "retmode": "json",
            "retmax": str(max_results),
        }
        response = await self._request("esearch.fcgi", search_params)
        try:
            id_list: list[str] = response.json()["esearchresult"]["idlist"]
        except (KeyError, ValueError, TypeError) as exc:
            raise MalformedPayloadError(
                f"NCBI esearch response for query {query!r} was not the "
                f"expected JSON shape: {exc}"
            ) from exc

        if not id_list:
            return []

        summary_params = {
            **self._common_params(),
            "db": self._db,
            "id": ",".join(id_list),
            "retmode": "json",
        }
        response = await self._request("esummary.fcgi", summary_params)
        try:
            result: dict[str, Any] = response.json()["result"]
        except (KeyError, ValueError, TypeError) as exc:
            raise MalformedPayloadError(
                f"NCBI esummary response for query {query!r} was not the "
                f"expected JSON shape: {exc}"
            ) from exc

        summaries: list[SequenceSummary] = []
        for uid in id_list:
            entry = result.get(uid)
            if not isinstance(entry, dict):
                continue
            accession = str(
                entry.get("caption") or entry.get("accessionversion") or uid
            )
            length_raw = entry.get("slen")
            length = int(length_raw) if isinstance(length_raw, int) else None
            summaries.append(
                SequenceSummary(
                    accession=accession,
                    title=str(entry.get("title", "")),
                    length=length,
                    source_database="ncbi",
                    metadata={"ncbi_esummary": entry},
                )
            )
        return summaries
