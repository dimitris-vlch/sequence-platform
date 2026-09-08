"""HTTP-layer tests for the Stage 6 ``GET /api/align`` endpoint.

The endpoint is driven with a mocked NCBI client over
``httpx.ASGITransport`` — no network. Aligning the 12 bp ``ACGTACGTACGT``
fixture record to itself yields a perfect global alignment (score 12.0).
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


def _align_params(**overrides):
    params = {
        "accession_a": "NM_000001.1",
        "accession_b": "NM_000001.1",
        "database": "ncbi",
        "mode": "global",
    }
    params.update(overrides)
    return params


@pytest.mark.asyncio
async def test_align_identical_record(ncbi_transport: httpx.MockTransport) -> None:
    """Global alignment of ACGTACGTACGT to itself: 12 matches, score 12.0."""
    async with _client(ncbi_transport) as client:
        response = await client.get("/api/align", params=_align_params())
    assert response.status_code == 200
    payload = response.json()
    assert payload["accession_a"] == "NM_000001.1"
    assert payload["accession_b"] == "NM_000001.1"
    assert payload["mode"] == "global"
    assert payload["score"] == pytest.approx(12.0)
    assert payload["aligned_a"] == "ACGTACGTACGT"
    assert payload["aligned_b"] == "ACGTACGTACGT"
    assert payload["start_a"] == 0
    assert payload["end_a"] == 12
    assert payload["start_b"] == 0
    assert payload["end_b"] == 12
    assert payload["match_score"] == 1.0
    assert payload["mismatch_score"] == -1.0
    assert payload["open_gap_score"] == -2.0
    assert payload["extend_gap_score"] == -0.5


@pytest.mark.asyncio
async def test_align_local_mode(ncbi_transport: httpx.MockTransport) -> None:
    """Local alignment of identical sequences also yields full match."""
    async with _client(ncbi_transport) as client:
        response = await client.get("/api/align", params=_align_params(mode="local"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "local"
    assert payload["score"] == pytest.approx(12.0)


@pytest.mark.asyncio
async def test_align_defaults_to_ncbi(ncbi_transport: httpx.MockTransport) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get("/api/align", params=_align_params(database=None))
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_align_defaults_to_global_mode(
    ncbi_transport: httpx.MockTransport,
) -> None:
    """Omitting the mode param should default to 'global'."""
    params = _align_params()
    del params["mode"]
    async with _client(ncbi_transport) as client:
        response = await client.get("/api/align", params=params)
    assert response.status_code == 200
    assert response.json()["mode"] == "global"


@pytest.mark.asyncio
async def test_align_custom_scores(ncbi_transport: httpx.MockTransport) -> None:
    """Custom scoring parameters are echoed back in the response."""
    async with _client(ncbi_transport) as client:
        response = await client.get(
            "/api/align",
            params=_align_params(
                match_score=2.0,
                mismatch_score=-2.0,
                open_gap_score=-4.0,
                extend_gap_score=-1.0,
            ),
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["match_score"] == 2.0
    assert payload["mismatch_score"] == -2.0
    assert payload["open_gap_score"] == -4.0
    assert payload["extend_gap_score"] == -1.0
    # 12 matches * 2.0 = 24.0 (identical sequences, no gaps)
    assert payload["score"] == pytest.approx(24.0)


@pytest.mark.asyncio
async def test_align_unknown_database(ncbi_transport: httpx.MockTransport) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get("/api/align", params=_align_params(database="ena"))
    assert response.status_code == 404
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_align_not_found(ncbi_not_found_transport: httpx.MockTransport) -> None:
    async with _client(ncbi_not_found_transport) as client:
        response = await client.get("/api/align", params=_align_params())
    assert response.status_code == 404
    assert "detail" in response.json()
