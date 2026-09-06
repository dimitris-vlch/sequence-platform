"""Tests for the Stage 4 analysis routes (statistics + quality).

Follows the ``test_databases.py`` pattern: the app is built in-process
with a mocked NCBI client and driven via ``httpx.ASGITransport`` — no
network. Expected values are the documented Stage 4 rules applied to the
12 bp ``ACGTACGTACGT`` fixture record.
"""

import httpx

from sequence_platform.database.ncbi.client import NCBISequenceDatabase
from sequence_platform.main import create_app


def _client(transport: httpx.MockTransport) -> httpx.AsyncClient:
    """Build an in-process client around the app with a mocked NCBI client."""
    ncbi = NCBISequenceDatabase(transport=transport)
    app = create_app(databases={"ncbi": ncbi})
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


async def test_statistics_endpoint(ncbi_transport: httpx.MockTransport) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get(
            "/api/sequences/NM_000001.1/statistics", params={"database": "ncbi"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["accession"] == "NM_000001.1"
    assert body["seq_type"] == "dna"
    assert body["length"] == 12
    assert body["gc_content"] == 50.0
    assert body["base_composition"] == {
        "A": 25.0,
        "C": 25.0,
        "G": 25.0,
        "T": 25.0,
        "ambiguous": 0.0,
    }
    assert body["ambiguous_count"] == 0
    assert body["ambiguous_percentage"] == 0.0
    assert body["n_run_count"] == 0
    assert body["longest_n_run"] == 0


async def test_statistics_requires_database_param(
    ncbi_transport: httpx.MockTransport,
) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get("/api/sequences/NM_000001.1/statistics")
    assert response.status_code == 422


async def test_statistics_unknown_database(ncbi_transport: httpx.MockTransport) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get(
            "/api/sequences/NM_000001.1/statistics", params={"database": "ena"}
        )
    assert response.status_code == 404
    assert "detail" in response.json()


async def test_statistics_not_found(
    ncbi_not_found_transport: httpx.MockTransport,
) -> None:
    async with _client(ncbi_not_found_transport) as client:
        response = await client.get(
            "/api/sequences/DOES_NOT_EXIST/statistics", params={"database": "ncbi"}
        )
    assert response.status_code == 404
    assert "detail" in response.json()


async def test_quality_endpoint(ncbi_transport: httpx.MockTransport) -> None:
    # 12 bp record: below the default 100 bp minimum; otherwise clean.
    async with _client(ncbi_transport) as client:
        response = await client.get(
            "/api/sequences/NM_000001.1/quality", params={"database": "ncbi"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["accession"] == "NM_000001.1"
    assert body["passed"] is False
    assert len(body["issues"]) == 1
    assert "length" in body["issues"][0]
    assert body["min_length"] == 100
    assert body["max_ambiguous_fraction"] == 0.1
    assert body["max_n_run"] == 10


async def test_quality_threshold_override(
    ncbi_transport: httpx.MockTransport,
) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get(
            "/api/sequences/NM_000001.1/quality",
            params={"database": "ncbi", "min_length": 5},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["issues"] == []
    assert body["min_length"] == 5


async def test_quality_fully_ambiguous_record(
    ambiguous_reference_transport: httpx.MockTransport,
) -> None:
    async with _client(ambiguous_reference_transport) as client:
        response = await client.get(
            "/api/sequences/AMB_0001.1/quality", params={"database": "ncbi"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    # 22 bp (short) + 100% ambiguous: at least these two checks fail.
    assert any("length" in issue for issue in body["issues"])
    assert any("ambiguous" in issue for issue in body["issues"])