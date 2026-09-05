"""Tests for the database-backed API routes.

Every test drives the ASGI app in-process via ``httpx.ASGITransport``
with a client map injected into ``create_app``; no test performs a real
network request (§2 external-service policy).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from conftest import (
    NCBI_TEST_ACCESSION,
    NCBI_TEST_SEQUENCE,
)
from sequence_platform.database.ncbi.client import NCBISequenceDatabase
from sequence_platform.main import create_app


def _app_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.AsyncClient:
    """Build an ``AsyncClient`` for ``create_app`` with a mocked NCBI client."""
    ncbi = NCBISequenceDatabase(
        email="test@example.com",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )
    app = create_app(databases={"ncbi": ncbi})
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
