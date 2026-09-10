"""Tests for ``ENASequenceDatabase`` against a mocked ``httpx`` transport.

No test in this module performs a real network request (§2 external-service
policy): every ``httpx.AsyncClient`` is constructed with an explicit mock
transport.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from conftest import (
    ENA_TEST_ACCESSION,
    ENA_TEST_DESCRIPTION,
    ENA_TEST_FASTA,
    ENA_TEST_SEARCH_ACCESSIONS,
    ENA_TEST_SEARCH_HITS,
    ENA_TEST_SEQUENCE,
)
from sequence_platform.database.ena.client import ENASequenceDatabase
from sequence_platform.database.exceptions import (
    AccessionNotFoundError,
    MalformedPayloadError,
    RateLimitedError,
    UpstreamUnavailableError,
)
from sequence_platform.models import SeqType


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_retries: int = 0,
    backoff_base: float = 0.0,
    backoff_cap: float = 0.0,
) -> ENASequenceDatabase:
    """Build a client wired to a mock transport, with retries fast/off.

    ``max_retries=0`` by default: most tests exercise a single request/
    response pair and should fail immediately rather than sleeping through
    retries. Tests that specifically exercise the retry policy override
    ``max_retries`` and keep ``backoff_base``/``backoff_cap`` at ``0.0`` so
    they run instantly instead of sleeping in real time.
    """
    return ENASequenceDatabase(
        transport=httpx.MockTransport(handler),
        max_retries=max_retries,
        backoff_base=backoff_base,
        backoff_cap=backoff_cap,
    )


async def test_fetch_happy_path(
    ena_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    client = _client(ena_happy_path_handler)
    record = await client.fetch(ENA_TEST_ACCESSION)
    assert record.accession == ENA_TEST_ACCESSION
    assert record.sequence == ENA_TEST_SEQUENCE
    assert record.description == ENA_TEST_DESCRIPTION
    assert record.seq_type == SeqType.DNA
    assert record.source_database == "ena"
    # Stage 9: the raw FASTA text and the request URL are retained for
    # provenance — ENA's counterpart of NCBI's `ncbi_esummary` entry.
    assert set(record.metadata) == {"ena_fasta_raw", "ena_request_url"}
    assert record.metadata["ena_fasta_raw"] == ENA_TEST_FASTA
    assert str(record.metadata["ena_request_url"]).endswith(
        f"/fasta/{ENA_TEST_ACCESSION}"
    )
    await client.close()


async def test_fetch_unknown_accession_raises_not_found(
    ena_not_found_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    client = _client(ena_not_found_handler)
    with pytest.raises(AccessionNotFoundError):
        await client.fetch("does-not-exist")
    await client.close()


async def test_fetch_malformed_fasta_raises_malformed_payload() -> None:
    """A 200 whose body is not usable FASTA is a 422, not a crash."""

    def handler(request: httpx.Request) -> httpx.Response:
        # Title line with no accession token: ``parse_fasta`` rejects it.
        return httpx.Response(200, text=">   \nACGT\n")

    client = _client(handler)
    with pytest.raises(MalformedPayloadError):
        await client.fetch(ENA_TEST_ACCESSION)
    await client.close()


async def test_fetch_empty_body_raises_malformed_payload() -> None:
    """A 200 with an empty body yields zero records, which is rejected."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="")

    client = _client(handler)
    with pytest.raises(MalformedPayloadError):
        await client.fetch(ENA_TEST_ACCESSION)
    await client.close()


async def test_fetch_multi_record_payload_raises_malformed_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=">a desc\nACGT\n>b desc\nTTTT\n")

    client = _client(handler)
    with pytest.raises(MalformedPayloadError):
        await client.fetch(ENA_TEST_ACCESSION)
    await client.close()


async def test_search_returns_hits(
    ena_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    client = _client(ena_happy_path_handler)
    hits = await client.search("test query")
    assert tuple(hit.accession for hit in hits) == ENA_TEST_SEARCH_ACCESSIONS
    first = hits[0]
    assert first.title == ENA_TEST_DESCRIPTION
    # ENA search hits carry no length; inventing one is never allowed.
    assert first.length is None
    assert first.source_database == "ena"
    # The raw hit is preserved verbatim for provenance fidelity.
    assert first.metadata == ENA_TEST_SEARCH_HITS[0]
    await client.close()


async def test_search_empty_hit_list_is_not_an_error(
    ena_not_found_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    client = _client(ena_not_found_handler)
    hits = await client.search("nothing matches this")
    assert hits == []
    await client.close()


async def test_search_non_array_payload_raises_malformed_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client = _client(handler)
    with pytest.raises(MalformedPayloadError):
        await client.search("test query")
    await client.close()


async def test_search_hit_without_accession_raises_malformed_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"description": "no accession here"}])

    client = _client(handler)
    with pytest.raises(MalformedPayloadError):
        await client.search("test query")
    await client.close()


async def test_5xx_is_retried_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500)
        return httpx.Response(
            200, text=ENA_TEST_FASTA, headers={"content-type": "text/plain"}
        )

    client = _client(handler, max_retries=1)
    record = await client.fetch(ENA_TEST_ACCESSION)
    assert record.sequence == ENA_TEST_SEQUENCE
    assert calls == 2
    await client.close()


async def test_5xx_exhausts_retries_and_raises_upstream_unavailable() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = _client(handler, max_retries=2)
    with pytest.raises(UpstreamUnavailableError):
        await client.fetch(ENA_TEST_ACCESSION)
    assert calls == 3  # initial attempt + 2 retries
    await client.close()


async def test_network_error_exhausts_retries_and_raises_upstream_unavailable() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection refused", request=request)

    client = _client(handler, max_retries=1)
    with pytest.raises(UpstreamUnavailableError):
        await client.fetch(ENA_TEST_ACCESSION)
    assert calls == 2  # initial attempt + 1 retry
    await client.close()


async def test_429_exhausts_retries_and_raises_rate_limited() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0"})

    client = _client(handler, max_retries=1)
    with pytest.raises(RateLimitedError) as exc_info:
        await client.fetch(ENA_TEST_ACCESSION)
    assert exc_info.value.retry_after == 0.0
    await client.close()


async def test_non_429_4xx_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400)

    client = _client(handler, max_retries=3)
    with pytest.raises(UpstreamUnavailableError):
        await client.fetch(ENA_TEST_ACCESSION)
    assert calls == 1  # never retried
    await client.close()
