"""HTTP-layer tests for the Stage 5 ``GET /api/compare`` endpoint.

The endpoint is driven with a mocked NCBI client over
``httpx.ASGITransport`` — no network. Comparing the 12 bp ``ACGTACGTACGT``
fixture record to itself yields identical sequences, so every similarity
metric is maximal (100.0) and every distance is 0.
"""

import httpx
import pytest
from fastapi import FastAPI

from sequence_platform.database.ncbi import NCBISequenceDatabase
from sequence_platform.main import create_app


def _client(transport: httpx.MockTransport) -> httpx.AsyncClient:
    application: FastAPI = create_app(
        databases={"ncbi": NCBISequenceDatabase(transport=transport)}
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    )


def _compare_params(**overrides):
    params = {
        "accession_a": "NM_000001.1",
        "accession_b": "NM_000001.1",
        "database": "ncbi",
        "k": 4,
    }
    params.update(overrides)
    return params


@pytest.mark.asyncio
async def test_compare_identical_record(ncbi_transport: httpx.MockTransport) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get("/api/compare", params=_compare_params())
    assert response.status_code == 200
    payload = response.json()
    assert payload["accession_a"] == "NM_000001.1"
    assert payload["accession_b"] == "NM_000001.1"
    assert payload["length_a"] == 12
    assert payload["length_b"] == 12
    assert payload["hamming_distance"] == 0
    assert payload["percent_identity"] == pytest.approx(100.0)
    assert payload["levenshtein_distance"] == 0
    assert payload["normalized_edit_similarity"] == pytest.approx(100.0)
    assert payload["jaccard_kmer_similarity"] == pytest.approx(100.0)
    assert payload["k"] == 4


@pytest.mark.asyncio
async def test_compare_defaults_to_ncbi(ncbi_transport: httpx.MockTransport) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get(
            "/api/compare", params=_compare_params(database=None)
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_compare_unknown_database(ncbi_transport: httpx.MockTransport) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get(
            "/api/compare", params=_compare_params(database="ena")
        )
    assert response.status_code == 404
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_compare_not_found(ncbi_not_found_transport: httpx.MockTransport) -> None:
    async with _client(ncbi_not_found_transport) as client:
        response = await client.get("/api/compare", params=_compare_params())
    assert response.status_code == 404
    assert "detail" in response.json()
