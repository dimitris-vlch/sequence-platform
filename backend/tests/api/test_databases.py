"""Tests for the database-backed API routes.

Every test drives the ASGI app in-process via ``httpx.ASGITransport``
with a client map injected into ``create_app``; no test performs a real
network request (§2 external-service policy).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from conftest import (
    ENA_TEST_ACCESSION,
    ENA_TEST_DESCRIPTION,
    ENA_TEST_SEQUENCE,
    NCBI_TEST_ACCESSION,
    NCBI_TEST_ESUMMARY_ENTRY,
    NCBI_TEST_SEQUENCE,
)
from sequence_platform.database.base import SequenceDatabase
from sequence_platform.database.ena.client import ENASequenceDatabase
from sequence_platform.database.ncbi.client import NCBISequenceDatabase
from sequence_platform.main import create_app


def _app_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    ena_handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> httpx.AsyncClient:
    """Build an ``AsyncClient`` for ``create_app`` with mocked clients.

    The mocked NCBI client is always injected. When ``ena_handler`` is given,
    a mocked ENA client is injected alongside it, so the ENA fetch/search
    routes are exercised end-to-end; otherwise the map holds NCBI only and
    ``ena`` is advertised with ``available: false`` (the Stage 3 behaviour).
    """
    ncbi = NCBISequenceDatabase(
        email="test@example.com",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )
    databases: dict[str, SequenceDatabase] = {"ncbi": ncbi}
    if ena_handler is not None:
        databases["ena"] = ENASequenceDatabase(
            transport=httpx.MockTransport(ena_handler), max_retries=0
        )
    app = create_app(databases=databases)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


async def test_list_databases_reports_ncbi_available(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with _app_client(ncbi_happy_path_handler) as client:
        response = await client.get("/api/databases")
    assert response.status_code == 200
    body = response.json()
    names = {entry["name"]: entry["available"] for entry in body["databases"]}
    assert names["ncbi"] is True
    assert names["ena"] is False


async def test_fetch_sequence_happy_path(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with _app_client(ncbi_happy_path_handler) as client:
        response = await client.get(
            f"/api/databases/ncbi/sequences/{NCBI_TEST_ACCESSION}"
        )
    assert response.status_code == 200
    body = response.json()
    assert body["accession"] == NCBI_TEST_ACCESSION
    assert body["sequence"] == NCBI_TEST_SEQUENCE
    assert body["source_database"] == "ncbi"
    # Compact provider metadata is NOT filtered out of the record response.
    assert body["metadata"] == {"ncbi_esummary": NCBI_TEST_ESUMMARY_ENTRY}


async def test_fetch_sequence_unknown_accession_returns_404(
    ncbi_not_found_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with _app_client(ncbi_not_found_handler) as client:
        response = await client.get("/api/databases/ncbi/sequences/does-not-exist")
    assert response.status_code == 404


async def test_fetch_sequence_unknown_database_returns_404(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with _app_client(ncbi_happy_path_handler) as client:
        response = await client.get(
            f"/api/databases/ena/sequences/{NCBI_TEST_ACCESSION}"
        )
    assert response.status_code == 404


async def test_search_returns_hits(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with _app_client(ncbi_happy_path_handler) as client:
        response = await client.get(
            "/api/databases/ncbi/search", params={"query": "test"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "test"
    assert len(body["results"]) == 1


async def test_search_empty_hits_is_200(
    ncbi_not_found_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with _app_client(ncbi_not_found_handler) as client:
        response = await client.get(
            "/api/databases/ncbi/search", params={"query": "nothing"}
        )
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_max_results_out_of_range_is_422(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with _app_client(ncbi_happy_path_handler) as client:
        response = await client.get(
            "/api/databases/ncbi/search",
            params={"query": "test", "max_results": 101},
        )
    assert response.status_code == 422


async def test_list_databases_reports_ena_available(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
    ena_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """With both clients injected, ``ena`` is advertised as available."""

    async with _app_client(
        ncbi_happy_path_handler, ena_handler=ena_happy_path_handler
    ) as client:
        response = await client.get("/api/databases")
    assert response.status_code == 200
    names = {
        entry["name"]: entry["available"] for entry in response.json()["databases"]
    }
    assert names["ncbi"] is True
    assert names["ena"] is True


async def test_fetch_sequence_ena_happy_path(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
    ena_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with _app_client(
        ncbi_happy_path_handler, ena_handler=ena_happy_path_handler
    ) as client:
        response = await client.get(
            f"/api/databases/ena/sequences/{ENA_TEST_ACCESSION}"
        )
    assert response.status_code == 200
    body = response.json()
    assert body["accession"] == ENA_TEST_ACCESSION
    assert body["sequence"] == ENA_TEST_SEQUENCE
    assert body["description"] == ENA_TEST_DESCRIPTION
    assert body["source_database"] == "ena"


async def test_fetch_sequence_ena_metadata_excludes_the_raw_payload(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
    ena_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """The oversized ENA payloads stay out of the plain fetch response.

    They remain on the domain record for export provenance (see
    ``test_exports.py``); only this compact projection drops them.
    """
    async with _app_client(
        ncbi_happy_path_handler, ena_handler=ena_happy_path_handler
    ) as client:
        response = await client.get(
            f"/api/databases/ena/sequences/{ENA_TEST_ACCESSION}"
        )
    assert response.status_code == 200
    body = response.json()
    assert "ena_fasta_raw" not in body["metadata"]
    assert "ena_request_url" not in body["metadata"]
    assert body["metadata"] == {}
    # The sequence itself is still present, exactly once.
    assert body["sequence"] == ENA_TEST_SEQUENCE
    assert body["description"] == ENA_TEST_DESCRIPTION


async def test_fetch_sequence_ena_unknown_accession_returns_404(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
    ena_not_found_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with _app_client(
        ncbi_happy_path_handler, ena_handler=ena_not_found_handler
    ) as client:
        response = await client.get("/api/databases/ena/sequences/does-not-exist")
    assert response.status_code == 404


async def test_search_ena_returns_hits(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
    ena_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with _app_client(
        ncbi_happy_path_handler, ena_handler=ena_happy_path_handler
    ) as client:
        response = await client.get(
            "/api/databases/ena/search", params={"query": "test"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "test"
    assert len(body["results"]) == 2
    assert body["results"][0]["accession"] == ENA_TEST_ACCESSION
    assert body["results"][0]["source_database"] == "ena"
    assert body["results"][0]["length"] is None


async def test_search_ena_empty_hits_is_200(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
    ena_not_found_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with _app_client(
        ncbi_happy_path_handler, ena_handler=ena_not_found_handler
    ) as client:
        response = await client.get(
            "/api/databases/ena/search", params={"query": "nothing"}
        )
    assert response.status_code == 200
    assert response.json()["results"] == []
