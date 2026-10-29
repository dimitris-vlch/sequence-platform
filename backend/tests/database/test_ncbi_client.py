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


async def test_fetch_restricts_esearch_to_accession_field(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """fetch() must not run a free-text esearch, which can resolve an
    accession-like term to an unrelated record."""
    terms: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            terms.append(request.url.params.get("term"))
        return ncbi_happy_path_handler(request)

    client = _client(handler)
    await client.fetch(NCBI_TEST_ACCESSION)
    assert terms == [f"{NCBI_TEST_ACCESSION}[accn]"]
    await client.close()


async def test_concurrent_fetches_of_one_accession_share_one_lookup(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """The detail view fetches record + statistics + QC at once; that must
    cost NCBI one esearch/esummary/efetch round trip, not three."""
    import asyncio

    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path.rsplit("/", 1)[-1])
        return ncbi_happy_path_handler(request)

    client = _client(handler)
    records = await asyncio.gather(
        *(client.fetch(NCBI_TEST_ACCESSION) for _ in range(3))
    )
    assert [r.sequence for r in records] == [NCBI_TEST_SEQUENCE] * 3
    assert records[0] is not records[1]  # callers get independent copies
    assert sorted(paths) == ["efetch.fcgi", "esearch.fcgi", "esummary.fcgi"]
    await client.fetch(NCBI_TEST_ACCESSION)  # served from cache
    assert len(paths) == 3
    await client.close()


async def test_failed_fetch_is_not_cached(
    ncbi_not_found_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return ncbi_not_found_handler(request)

    client = _client(handler)
    for _ in range(2):
        with pytest.raises(AccessionNotFoundError):
            await client.fetch("NOPE_1")
    assert calls == 2
    await client.close()


async def test_requests_are_spaced_by_min_interval(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    import asyncio

    loop = asyncio.get_running_loop()
    starts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        starts.append(loop.time())
        return ncbi_happy_path_handler(request)

    client = NCBISequenceDatabase(
        transport=httpx.MockTransport(handler), max_retries=0, min_interval=0.05
    )
    await client.fetch(NCBI_TEST_ACCESSION)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert len(gaps) == 2 and min(gaps) >= 0.045
    await client.close()
