"""ENA (European Nucleotide Archive) REST client.

Stage 7. Implements the ``SequenceDatabase`` interface (``database/base.py``)
against ENA's browser REST API, completing the second provider that
``registry.py`` advertises.

Endpoints (fixed in Stage 7; no live probing, §2)
-------------------------------------------------
- ``GET /fasta/{accession}`` — the record directly as plain FASTA text
  (no JSON envelope). A non-existent accession returns HTTP 404, which maps
  directly to ``AccessionNotFoundError`` (unlike NCBI's quirky 400, there is
  no ambiguity here).
- ``GET /search?query=...&result=sequence&format=json&limit=...`` — a JSON
  array of hit objects, each carrying at least an ``accession`` and a
  ``description``. An empty result is HTTP 200 with ``[]`` (there is no
  count field to gate on the way NCBI's esearch has; the empty array is
  itself the "no hits" signal).

ENA does not require an email/API-key courtesy parameter the way NCBI does,
so the constructor has no ``tool``/``email``/``api_key`` parameters and no
``Settings`` fields are needed for it.

``fetch`` deliberately makes a single request: the platform trusts
``parse_fasta``'s output as the source of truth for sequence content (the
Stage 3 NCBI provenance pattern), so no second metadata call is issued.

Stage 9 (export and provenance) added the payload retention NCBI already
had: ``fetch`` keeps the raw response text and the request URL under
``metadata["ena_fasta_raw"]`` and ``metadata["ena_request_url"]``, so an
exported ENA record can be traced back to exactly what ENA returned (§4).
This is ENA's counterpart of NCBI's ``metadata["ncbi_esummary"]``; the value
is raw FASTA text rather than a parsed JSON entry because ``/fasta`` returns
text and nothing else.

Retry policy (identical to the NCBI client, §2)
-----------------------------------------------
- 5xx, timeouts, and network errors: retry with exponential backoff
  (``backoff_base * 2**attempt`` capped at ``backoff_cap``, multiplied by a
  uniform jitter in [0.5, 1.5]); after ``max_retries`` retries raise
  ``UpstreamUnavailableError``.
- HTTP 429: honour ``Retry-After`` when present; after exhaustion raise
  ``RateLimitedError``.
- Any other 4xx: no retry, immediate ``UpstreamUnavailableError``.
- HTTP 404: no retry, immediate ``AccessionNotFoundError``.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, ClassVar

import httpx

from sequence_platform.database.base import SequenceDatabase, SequenceSummary
from sequence_platform.database.exceptions import (
    AccessionNotFoundError,
    MalformedPayloadError,
    RateLimitedError,
    UpstreamUnavailableError,
)
from sequence_platform.database.ncbi.fasta import parse_fasta
from sequence_platform.models import SequenceRecord

#: Default base URL for ENA's browser REST API.
DEFAULT_ENA_BASE_URL = "https://www.ebi.ac.uk/ena/browser/api"


class ENASequenceDatabase(SequenceDatabase):
    """Client for the ENA browser REST API.

    Mirrors ``NCBISequenceDatabase`` structurally: same constructor shape
    (minus NCBI's courtesy parameters, which ENA does not require), same
    retry/backoff policy, same exception mapping, same provenance stamping.

    Args:
        base_url: Base URL of the ENA browser API. Defaults to the public
            ENA endpoint; override for tests or mirrors.
        timeout: Per-request timeout in seconds.
        max_retries: Number of retries after the initial attempt for
            transient failures (5xx, timeouts, network errors, 429).
        backoff_base: Base delay in seconds for exponential backoff.
        backoff_cap: Upper bound in seconds for a single backoff delay.
        transport: Optional ``httpx.AsyncBaseTransport``; tests inject
            ``httpx.MockTransport`` so no real network request is made.
    """

    name: ClassVar[str] = "ena"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_ENA_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        backoff_cap: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._client = httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            headers={"Accept": "text/plain, application/json"},
        )

    async def close(self) -> None:
        """Release the underlying HTTP client."""
        await self._client.aclose()

    async def fetch(self, accession: str) -> SequenceRecord:
        """Fetch one record by accession.

        Args:
            accession: An ENA accession (e.g. an ENA sequence identifier).

        Returns:
            The fetched record with ``source_database="ena"`` stamped. The
            sequence content and length come from the parsed FASTA itself,
            which is the source of truth (Stage 3 provenance pattern); no
            second metadata call is made. The raw response text and the
            request URL are retained in ``metadata`` for provenance (§4).

        Raises:
            AccessionNotFoundError: If ENA returns 404 for the accession.
            MalformedPayloadError: If the response is not exactly one valid
                FASTA record.
            UpstreamUnavailableError / RateLimitedError: On exhausted
                transient failures, per the module docstring.
        """
        url = f"{self._base_url}/fasta/{accession}"
        response = await self._request("GET", url)
        try:
            records = parse_fasta(response.text, infer_seq_type=True)
        except ValueError as exc:
            raise MalformedPayloadError(
                f"ENA FASTA for {accession!r} failed to parse: {exc}"
            ) from exc
        if len(records) != 1:
            raise MalformedPayloadError(
                f"Expected exactly one FASTA record from ENA for accession "
                f"{accession!r}, got {len(records)}"
            )
        record = records[0]
        record.source_database = self.name
        record.metadata = {
            "ena_fasta_raw": response.text,
            "ena_request_url": url,
        }
        return record

    async def search(
        self, query: str, *, max_results: int = 20
    ) -> list[SequenceSummary]:
        """Search ENA by free-text query.

        Args:
            query: Free-text query for ENA's search endpoint.
            max_results: Upper bound on the number of summaries returned;
                passed through as the endpoint's ``limit`` parameter.

        Returns:
            One summary per hit, in the order ENA returns them. ``length``
            is ``None`` (search hits do not carry it, and fetching each
            hit's FASTA just for a length would defeat the purpose of a
            lightweight search); the raw hit object is preserved in
            ``metadata``. An empty hit list is a normal, non-error result.

        Raises:
            MalformedPayloadError: If the response is not a JSON array of
                hit objects with an ``accession`` field.
            UpstreamUnavailableError / RateLimitedError: On exhausted
                transient failures, per the module docstring.
        """
        response = await self._request(
            "GET",
            f"{self._base_url}/search",
            params={
                "query": query,
                "result": "sequence",
                "format": "json",
                "limit": max_results,
            },
        )
        payload = _parse_json(response, "search")
        if not isinstance(payload, list):
            raise MalformedPayloadError(
                f"Expected a JSON array of hits from ENA search, "
                f"got {type(payload).__name__}"
            )
        return [self._summary_from_hit(hit) for hit in payload]

    def _summary_from_hit(self, hit: Any) -> SequenceSummary:
        """Map one raw search hit to a ``SequenceSummary``.

        Raises:
            MalformedPayloadError: If the hit is not an object or lacks a
                usable ``accession``.
        """
        if not isinstance(hit, dict):
            raise MalformedPayloadError(
                f"Expected a JSON object for an ENA search hit, got {type(hit).__name__}"
            )
        accession = hit.get("accession")
        if not isinstance(accession, str) or not accession:
            raise MalformedPayloadError(
                f"ENA search hit is missing a usable accession field: {hit!r}"
            )
        description = hit.get("description")
        return SequenceSummary(
            accession=accession,
            title=description if isinstance(description, str) else "",
            length=None,
            source_database=self.name,
            metadata=dict(hit),
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Perform one HTTP request with the shared retry/backoff policy.

        Mirrors ``NCBISequenceDatabase._request`` exactly (same status-code
        handling, same exponential backoff with uniform jitter); ENA simply
        does not need NCBI's ``tool``/``email`` query parameters.

        Returns:
            The successful (2xx) response.

        Raises:
            AccessionNotFoundError: On HTTP 404 (no retry).
            RateLimitedError: On HTTP 429 after ``max_retries`` retries.
            UpstreamUnavailableError: On 5xx / network errors after
                ``max_retries`` retries, or on any other 4xx (no retry).
        """
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, url, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self._max_retries:
                    raise UpstreamUnavailableError(
                        f"ENA request to {url} failed after "
                        f"{self._max_retries} retries: {exc}"
                    ) from exc
                await self._backoff(attempt, None)
                attempt += 1
                continue

            if response.status_code == 404:
                raise AccessionNotFoundError(f"ENA returned 404 for {url}")

            if response.status_code == 429:
                retry_after = self._parse_retry_after(response)
                if attempt >= self._max_retries:
                    raise RateLimitedError(
                        f"ENA rate-limited requests to {url} after "
                        f"{self._max_retries} retries",
                        retry_after=retry_after,
                    )
                await self._backoff(attempt, retry_after)
                attempt += 1
                continue

            if response.status_code >= 500:
                if attempt >= self._max_retries:
                    raise UpstreamUnavailableError(
                        f"ENA returned {response.status_code} for {url} "
                        f"after {self._max_retries} retries"
                    )
                await self._backoff(attempt, None)
                attempt += 1
                continue

            if response.status_code >= 400:
                # Non-429 4xx: never retried (a 400/403 will not succeed
                # on retry). 404 was handled above.
                raise UpstreamUnavailableError(
                    f"ENA returned {response.status_code} for {url}"
                )

            return response

    async def _backoff(self, attempt: int, retry_after: float | None) -> None:
        """Sleep before the next retry, mirroring the NCBI client's policy.

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


def _parse_json(response: httpx.Response, step: str) -> Any:
    """Decode a JSON response body, mapping malformed payloads."""
    try:
        return response.json()
    except ValueError as exc:
        raise MalformedPayloadError(f"Malformed JSON from ENA {step}: {exc}") from exc
