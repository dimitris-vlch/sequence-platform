"""Tests for the /api/health endpoint."""

from httpx import ASGITransport, AsyncClient

from sequence_platform import __version__


async def test_health_reports_ok() -> None:
    """The health endpoint must report liveness with a stable schema."""
    from sequence_platform.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "sequence-platform"
    assert payload["version"] == __version__
    assert payload["databases"] == ["ncbi", "ena"]
    assert payload["time"]
