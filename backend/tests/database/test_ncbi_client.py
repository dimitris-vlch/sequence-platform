"""Tests for ``NCBISequenceDatabase`` against a mocked ``httpx`` transport.

No test in this module performs a real network request (§2 external-
service policy): every ``httpx.AsyncClient`` is constructed with an
explicit mock transport.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from conftest import (
    NCBI_TEST_ACCESSION,
    NCBI_TEST_ESUMMARY_ENTRY,
    NCBI_TEST_SEQUENCE,
    NCBI_TEST_UID,
)
from sequence_platform.database.exceptions import (
    AccessionNotFoundError,
    MalformedPayloadError,
    RateLimitedError,
    UpstreamUnavailableError,
)
from sequence_platform.database.ncbi.client import NCBISequenceDatabase
from sequence_platform.models import SeqType


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_retries: int = 0,
    backoff_base: float = 0.0,
    backoff_cap: float = 0.0,
) -> NCBISequenceDatabase:
    """Build a client wired to a mock transport, with retries fast/off.

    ``max_retries=0`` by default: most tests exercise a single request/
    response pair and should fail immediately rather than sleeping through
    retries. Tests that specifically exercise the retry policy override
    ``max_retries`` and keep ``backoff_base``/``backoff_cap`` at ``0.0`` so
    they run instantly instead of sleeping in real time.
    """
    return NCBISequenceDatabase(
        email="test@example.com",
        transport=httpx.MockTransport(handler),
        max_retries=max_retries,
        backoff_base=backoff_base,
        backoff_cap=backoff_cap,
    )


async def test_fetch_happy_path(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    client = _client(ncbi_happy_path_handler)
    record = await client.fetch(NCBI_TEST_ACCESSION)
    assert record.accession == NCBI_TEST_ACCESSION
    assert record.sequence == NCBI_TEST_SEQUENCE
    assert record.seq_type == SeqType.DNA
    assert record.source_database == "ncbi"
    assert record.metadata == {"ncbi_esummary": NCBI_TEST_ESUMMARY_ENTRY}
    await client.close()


async def test_fetch_unknown_accession_raises_not_found(
    ncbi_not_found_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    client = _client(ncbi_not_found_handler)
    with pytest.raises(AccessionNotFoundError):
        await client.fetch("does-not-exist")
    await client.close()


async def test_search_returns_hits(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    client = _client(ncbi_happy_path_handler)
    hits = await client.search("test query")
    assert len(hits) == 1
    hit = hits[0]
    assert hit.accession == "NM_000001"
    assert hit.length == len(NCBI_TEST_SEQUENCE)
    assert hit.source_database == "ncbi"
    await client.close()


async def test_search_empty_hit_list_is_not_an_error(
    ncbi_not_found_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    client = _client(ncbi_not_found_handler)
    hits = await client.search("nothing matches this")
    assert hits == []
    await client.close()


async def test_esummary_failure_leaves_metadata_empty_but_still_fetches() -> None:
    """A broken esummary response must not fail the whole fetch."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(
                200,
                json={
                    "esearchresult": {
                        "count": "1",
                        "idlist": [NCBI_TEST_UID],
                    }
                },
            )
        if request.url.path.endswith("esummary.fcgi"):
            return httpx.Response(500)
        if request.url.path.endswith("efetch.fcgi"):
            return httpx.Response(
                200,
                text=f">{NCBI_TEST_ACCESSION} desc\n{NCBI_TEST_SEQUENCE}\n",
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client(handler)
    record = await client.fetch(NCBI_TEST_ACCESSION)
    assert record.metadata == {}
    await client.close()


async def test_5xx_exhausts_retries_and_raises_upstream_unavailable() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = _client(handler, max_retries=2)
    with pytest.raises(UpstreamUnavailableError):
        await client.fetch(NCBI_TEST_ACCESSION)
    assert calls == 3  # initial attempt + 2 retries
    await client.close()


async def test_429_exhausts_retries_and_raises_rate_limited() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0"})

    client = _client(handler, max_retries=1)
    with pytest.raises(RateLimitedError) as exc_info:
        await client.fetch(NCBI_TEST_ACCESSION)
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
        await client.fetch(NCBI_TEST_ACCESSION)
    assert calls == 1  # never retried
    await client.close()


async def test_malformed_esearch_json_raises_malformed_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client = _client(handler)
    with pytest.raises(MalformedPayloadError):
        await client.fetch(NCBI_TEST_ACCESSION)
    await client.close()


async def test_efetch_multi_record_payload_raises_malformed_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(
                200,
                json={"esearchresult": {"count": "1", "idlist": [NCBI_TEST_UID]}},
            )
        if request.url.path.endswith("esummary.fcgi"):
            return httpx.Response(200, json={"result": {NCBI_TEST_UID: {}}})
        if request.url.path.endswith("efetch.fcgi"):
            return httpx.Response(200, text=">a\nACGT\n>b\nTTTT\n")
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client(handler)
    with pytest.raises(MalformedPayloadError):
        await client.fetch(NCBI_TEST_ACCESSION)
    await client.close()
