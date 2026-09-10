"""Production-hardening integration tests: error mapping and logging.

Stage 10 Part B, items 1 and 4, verified through the real ASGI stack rather
than by unit-testing a handler in isolation: the app is built with a mocked
provider client and driven with ``httpx``.

``raise_app_exceptions=False`` is used for the unhandled-fault case only, so
the test observes the *response an HTTP client would receive*; the default
in httpx is to re-raise into the test, which is what every other test here
relies on.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import ClassVar

import httpx
import pytest

from conftest import (
    NCBI_TEST_ACCESSION,
    NCBI_TEST_ESUMMARY_ENTRY,
    NCBI_TEST_FASTA,
    NCBI_TEST_UID,
)
from sequence_platform.database.base import SequenceDatabase, SequenceSummary
from sequence_platform.database.ncbi.client import NCBISequenceDatabase
from sequence_platform.main import create_app
from sequence_platform.models import SequenceRecord

#: The module logger of the NCBI client, asserted on by the retry tests.
NCBI_LOGGER_NAME = "sequence_platform.database.ncbi.client"

_ESEARCH_OK = httpx.Response(
    200,
    json={
        "esearchresult": {
            "count": "1",
            "retmax": "1",
            "retstart": "0",
            "idlist": [NCBI_TEST_UID],
        }
    },
)
_ESUMMARY_OK = httpx.Response(
    200,
    json={"result": {"uids": [NCBI_TEST_UID], NCBI_TEST_UID: NCBI_TEST_ESUMMARY_ENTRY}},
)


def _transient_ncbi_handler(
    status: int, *, headers: dict[str, str] | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    """Answer the first ``esearch`` with ``status``, then serve the happy path."""
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("esearch.fcgi"):
            attempts.append(1)
            if len(attempts) == 1:
                return httpx.Response(status, headers=headers or {})
            return _ESEARCH_OK
        if path.endswith("esummary.fcgi"):
            return _ESUMMARY_OK
        if path.endswith("efetch.fcgi"):
            return httpx.Response(200, text=NCBI_TEST_FASTA)
        raise AssertionError(f"unexpected NCBI request: {request.url}")

    return handler


class _ExplodingDatabase(SequenceDatabase):
    """A provider client whose every call raises, for the 500-path test."""

    name: ClassVar[str] = "exploding"

    async def fetch(self, accession: str) -> SequenceRecord:
        raise RuntimeError("simulated internal fault while fetching")

    async def search(
        self, query: str, *, max_results: int = 20
    ) -> list[SequenceSummary]:
        raise RuntimeError("simulated internal fault while searching")


def _client(
    databases: dict[str, SequenceDatabase], *, raise_app_exceptions: bool = True
) -> httpx.AsyncClient:
    app = create_app(databases=databases)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=app, raise_app_exceptions=raise_app_exceptions
        ),
        base_url="http://testserver",
    )


def _ncbi_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_retries: int = 0,
) -> NCBISequenceDatabase:
    return NCBISequenceDatabase(
        email="test@example.com",
        transport=httpx.MockTransport(handler),
        max_retries=max_retries,
        backoff_base=0.0,  # no real sleeping in tests
    )


#: A 10 bp record: shorter than the largest ``k`` the compare route accepts
#: (``k`` is bounded by ``Query(le=12)``), which is the reachable case where
#: the analysis layer refuses to form k-mers.
SHORT_ACCESSION = "NM_000002.1"
SHORT_FASTA = f">{SHORT_ACCESSION} synthetic short record\nACGTACGTAC\n"


def _short_record_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("esearch.fcgi"):
        return httpx.Response(
            200,
            json={
                "esearchresult": {
                    "count": "1",
                    "retmax": "1",
                    "retstart": "0",
                    "idlist": ["222"],
                }
            },
        )
    if path.endswith("esummary.fcgi"):
        return httpx.Response(
            200,
            json={
                "result": {
                    "uids": ["222"],
                    "222": {
                        "uid": "222",
                        "caption": SHORT_ACCESSION,
                        "title": "synthetic short record",
                        "slen": 10,
                    },
                }
            },
        )
    if path.endswith("efetch.fcgi"):
        return httpx.Response(200, text=SHORT_FASTA)
    raise AssertionError(f"unexpected NCBI request: {request.url}")


async def test_k_larger_than_a_short_record_is_a_clean_422() -> None:
    """A caller-supplied ``k`` the record cannot satisfy is a 422, not a fault.

    ``analysis/similarity`` raises a plain ``ValueError`` when a non-empty
    sequence is shorter than ``k``; both routes that reach it must answer with
    the platform's error shape instead of letting it escape as a 500.
    """
    async with _client({"ncbi": _ncbi_client(_short_record_handler)}) as client:
        params: dict[str, str | int] = {
            "accession_a": SHORT_ACCESSION,
            "database": "ncbi",
            "k": 11,
        }
        for url in ("/api/compare", "/api/export/compare/json"):
            response = await client.get(url, params=params)
            assert response.status_code == 422, url
            assert "shorter than k" in response.json()["detail"], url


async def test_unexpected_error_becomes_a_json_500_and_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unforeseen fault: JSON body for the client, traceback for the log."""
    caplog.set_level(logging.INFO)
    databases: dict[str, SequenceDatabase] = {"exploding": _ExplodingDatabase()}
    async with _client(databases, raise_app_exceptions=False) as client:
        response = await client.get("/api/databases/exploding/sequences/X")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert "Traceback" not in response.text

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors, "an unexpected fault must reach the server log"
    logged = errors[-1]
    assert logged.getMessage() == (
        "Unhandled error serving GET /api/databases/exploding/sequences/X"
    )
    # The traceback, including the original exception, stays server-side.
    assert logged.exc_info is not None
    assert isinstance(logged.exc_info[1], RuntimeError)


async def test_requests_are_logged_with_method_path_and_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every request emits one application-level access line."""
    caplog.set_level(logging.INFO)
    async with _client({}) as client:
        await client.get("/api/health")

    lines = [
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("sequence_platform")
    ]
    assert any("GET /api/health" in line and "200" in line for line in lines)


async def test_upstream_retry_is_logged_and_the_request_still_succeeds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A transient 5xx is retried, logged, and invisible to the caller."""
    caplog.set_level(logging.INFO)
    databases: dict[str, SequenceDatabase] = {
        "ncbi": _ncbi_client(_transient_ncbi_handler(503), max_retries=1)
    }
    async with _client(databases) as client:
        response = await client.get(
            f"/api/databases/ncbi/sequences/{NCBI_TEST_ACCESSION}"
        )

    assert response.status_code == 200
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name == NCBI_LOGGER_NAME and record.levelno == logging.WARNING
    ]
    assert any("503" in line and "retry" in line for line in warnings)


async def test_upstream_rate_limit_backoff_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 429 is retried after honouring ``Retry-After``, and logged as such."""
    caplog.set_level(logging.INFO)
    databases: dict[str, SequenceDatabase] = {
        "ncbi": _ncbi_client(
            _transient_ncbi_handler(429, headers={"Retry-After": "0"}), max_retries=1
        )
    }
    async with _client(databases) as client:
        response = await client.get(
            f"/api/databases/ncbi/sequences/{NCBI_TEST_ACCESSION}"
        )

    assert response.status_code == 200
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name == NCBI_LOGGER_NAME and record.levelno == logging.WARNING
    ]
    assert any("429" in line and "Retry-After" in line for line in warnings)
