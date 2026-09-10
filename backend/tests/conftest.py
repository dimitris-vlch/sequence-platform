"""Shared pytest fixtures for the backend test suite.

The shared hand-designed reference sequences used by known-answer tests
live here, not copy-pasted into individual test files.

The NCBI and ENA fixtures below are synthetic: no fixture ever performs a
real network request. ``httpx.MockTransport`` intercepts every call the
client would otherwise make to the live E-utilities / ENA APIs (§2
external-service policy: never a real external request from a committed
test).
"""

from collections.abc import Callable

import httpx
import pytest

from sequence_platform.models import SeqType, SequenceRecord

#: A synthetic accession/UID pair used across the NCBI client and route
#: tests, paired with hand-built esearch/esummary/efetch responses below.
NCBI_TEST_ACCESSION = "NM_000001.1"
NCBI_TEST_UID = "12345"
NCBI_TEST_SEQUENCE = "ACGTACGTACGT"

#: Synthetic esummary entry for ``NCBI_TEST_UID``, shaped like a real NCBI
#: esummary.fcgi JSON entry (subset of fields actually used by the client).
NCBI_TEST_ESUMMARY_ENTRY = {
    "uid": NCBI_TEST_UID,
    "caption": "NM_000001",
    "title": "Homo sapiens test gene (TEST), mRNA",
    "slen": len(NCBI_TEST_SEQUENCE),
    "organism": "Homo sapiens",
}

NCBI_TEST_FASTA = (
    f">{NCBI_TEST_ACCESSION} Homo sapiens test gene (TEST), mRNA\n"
    f"{NCBI_TEST_SEQUENCE}\n"
)


def _esearch_json(*, uids: list[str]) -> dict[str, object]:
    """Build an esearch.fcgi-shaped JSON payload for ``uids``."""
    return {
        "esearchresult": {
            "count": str(len(uids)),
            "retmax": str(len(uids)),
            "retstart": "0",
            "idlist": uids,
        }
    }


def _esummary_json(*, entries: dict[str, dict[str, object]]) -> dict[str, object]:
    """Build an esummary.fcgi-shaped JSON payload for ``entries``."""
    return {"result": {"uids": list(entries), **entries}}


@pytest.fixture
def ncbi_happy_path_handler() -> Callable[[httpx.Request], httpx.Response]:
    """A transport handler that resolves ``NCBI_TEST_ACCESSION`` normally.

    Routes by the E-utilities endpoint name in the request path: esearch
    always finds ``NCBI_TEST_UID``, esummary returns
    ``NCBI_TEST_ESUMMARY_ENTRY`` for it, and efetch returns
    ``NCBI_TEST_FASTA``. Any other endpoint raises, so a test that hits an
    unexpected endpoint fails loudly instead of silently.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json=_esearch_json(uids=[NCBI_TEST_UID]))
        if request.url.path.endswith("esummary.fcgi"):
            return httpx.Response(
                200,
                json=_esummary_json(entries={NCBI_TEST_UID: NCBI_TEST_ESUMMARY_ENTRY}),
            )
        if request.url.path.endswith("efetch.fcgi"):
            return httpx.Response(
                200, text=NCBI_TEST_FASTA, headers={"content-type": "text/plain"}
            )
        raise AssertionError(f"unexpected NCBI request: {request.url}")

    return handler


@pytest.fixture
def ncbi_not_found_handler() -> Callable[[httpx.Request], httpx.Response]:
    """A transport handler where esearch reports zero hits for any query."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json=_esearch_json(uids=[]))
        raise AssertionError(f"unexpected NCBI request: {request.url}")

    return handler


@pytest.fixture
def ncbi_transport(
    ncbi_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    """A ready-to-use mock transport for the happy path."""
    return httpx.MockTransport(ncbi_happy_path_handler)


@pytest.fixture
def ncbi_not_found_transport(
    ncbi_not_found_handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    """A ready-to-use mock transport where every accession misses."""
    return httpx.MockTransport(ncbi_not_found_handler)


@pytest.fixture
def ambiguous_reference_transport() -> httpx.MockTransport:
    """A mock transport serving an ambiguity-only reference end-to-end.

    Mirrors ``ncbi_happy_path_handler`` for a second synthetic record
    whose sequence consists solely of IUPAC ambiguity codes: esearch
    finds the UID, esummary returns a minimal entry, and efetch returns
    the matching FASTA text.
    """
    accession = "AMB_0001.1"
    uid = "55555"
    sequence = "RYSWKMBDHVN" * 2
    fasta = f">{accession} reference assembled from ambiguity codes only\n{sequence}\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json=_esearch_json(uids=[uid]))
        if request.url.path.endswith("esummary.fcgi"):
            return httpx.Response(
                200,
                json=_esummary_json(
                    entries={
                        uid: {
                            "uid": uid,
                            "caption": "AMB_0001",
                            "title": "reference assembled from ambiguity codes only",
                            "slen": len(sequence),
                        }
                    }
                ),
            )
        if request.url.path.endswith("efetch.fcgi"):
            return httpx.Response(
                200, text=fasta, headers={"content-type": "text/plain"}
            )
        raise AssertionError(f"unexpected NCBI request: {request.url}")

    return httpx.MockTransport(handler)


@pytest.fixture
def all_nucleotides() -> SequenceRecord:
    """A record covering all 15 IUPAC nucleotide codes, each exactly once.

    The four unambiguous bases (``ACGT``) plus the eleven ambiguity codes
    (``RYSWKMBDHVN``), in IUPAC table order.
    """
    return SequenceRecord(
        accession="NM_000001",
        sequence="ACGTRYSWKMBDHVN",
        seq_type=SeqType.DNA,
        title="NM_000001 all IUPAC nucleotide codes",
        description="all IUPAC nucleotide codes",
        source_database="",
        metadata={},
    )


@pytest.fixture
def ambiguous_reference() -> SequenceRecord:
    """A record whose sequence uses only IUPAC ambiguity codes.

    The eleven ambiguity codes (``RYSWKMBDHVN``) repeated twice; it
    contains no unambiguous bases.
    """
    return SequenceRecord(
        accession="R_1",
        sequence="RYSWKMBDHVN" * 2,
        seq_type=SeqType.DNA,
        title="R_1 reference assembled from ambiguity codes only",
        description="reference assembled from ambiguity codes only",
        source_database="",
        metadata={},
    )


# --------------------------------------------------------------------------
# ENA fixtures (Stage 7)
#
# Synthetic accession, FASTA text, and search payload, shaped like ENA's
# browser REST API responses as fixed for Stage 7. No fixture reaches the
# network: the handlers below are served through ``httpx.MockTransport``.
# --------------------------------------------------------------------------

#: A synthetic ENA accession used across the ENA client and route tests.
ENA_TEST_ACCESSION = "AB000001.1"
ENA_TEST_SEQUENCE = "ACGTACGTACGT"
ENA_TEST_DESCRIPTION = "synthetic ENA test record"

#: ENA's ``GET /fasta/{accession}`` response: plain FASTA text, one record,
#: no JSON envelope (the header is the plain ``>ACCESSION description``
#: convention ``parse_fasta`` already handles).
ENA_TEST_FASTA = f">{ENA_TEST_ACCESSION} {ENA_TEST_DESCRIPTION}\n{ENA_TEST_SEQUENCE}\n"

#: ENA's ``GET /search?...&format=json`` response: a top-level JSON array of
#: hit objects, each with at least ``accession`` and ``description``.
ENA_TEST_SEARCH_HITS: list[dict[str, object]] = [
    {"accession": ENA_TEST_ACCESSION, "description": ENA_TEST_DESCRIPTION},
    {"accession": "AB000002.1", "description": "second synthetic ENA test record"},
]

#: Accessions of the synthetic search hits, in the order ENA returns them.
ENA_TEST_SEARCH_ACCESSIONS: tuple[str, ...] = tuple(
    str(hit["accession"]) for hit in ENA_TEST_SEARCH_HITS
)


@pytest.fixture
def ena_happy_path_handler() -> Callable[[httpx.Request], httpx.Response]:
    """A transport handler that resolves ``ENA_TEST_ACCESSION`` normally.

    Routes by the browser-API path: ``/fasta/{accession}`` returns
    ``ENA_TEST_FASTA`` and ``/search`` returns ``ENA_TEST_SEARCH_HITS``. Any
    other path raises, so a test that hits an unexpected endpoint fails
    loudly instead of silently.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(f"/fasta/{ENA_TEST_ACCESSION}"):
            return httpx.Response(
                200, text=ENA_TEST_FASTA, headers={"content-type": "text/plain"}
            )
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json=ENA_TEST_SEARCH_HITS)
        raise AssertionError(f"unexpected ENA request: {request.url}")

    return handler


@pytest.fixture
def ena_not_found_handler() -> Callable[[httpx.Request], httpx.Response]:
    """A transport handler for the two normal "nothing there" outcomes.

    A fetch of any accession returns HTTP 404 (ENA's not-found signal) and a
    search returns HTTP 200 with an empty array (an empty result is not an
    error for ENA, unlike NCBI's count-gated esearch).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if "/fasta/" in request.url.path:
            return httpx.Response(404)
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected ENA request: {request.url}")

    return handler


@pytest.fixture
def ena_transport(
    ena_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    """A ready-to-use mock transport for the ENA happy path."""
    return httpx.MockTransport(ena_happy_path_handler)


@pytest.fixture
def ena_not_found_transport(
    ena_not_found_handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    """A ready-to-use mock transport where fetches miss and searches are empty."""
    return httpx.MockTransport(ena_not_found_handler)
