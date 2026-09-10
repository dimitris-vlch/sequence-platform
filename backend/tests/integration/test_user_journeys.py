"""End-to-end journeys through the whole ASGI application (Stage 10).

These tests are a different layer from the ones already in the suite. The
``tests/api/`` tests exercise one endpoint per test against a freshly built
app; ``tests/database`` and ``tests/analysis`` exercise one layer. Here the
application is built **once** and a realistic multi-step user flow walks
through it — list databases → search → fetch → statistics → quality →
compare → align → export — asserting that the endpoints agree *with each
other*. Cross-route agreement is the property no single-route test can
observe, and precisely the one that would silently break if the Stage 9
shared response builders drifted from the read endpoints.

Every provider call is intercepted by ``httpx.MockTransport`` (§2); no test
performs a real external request.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

import httpx

from conftest import ENA_TEST_ACCESSION, ENA_TEST_FASTA, NCBI_TEST_ACCESSION
from sequence_platform.database.base import SequenceDatabase
from sequence_platform.database.ena.client import ENASequenceDatabase
from sequence_platform.database.ncbi.client import NCBISequenceDatabase
from sequence_platform.main import create_app

#: Second synthetic NCBI accession. The shared conftest handlers resolve
#: *any* accession to the same record, which is all a single-endpoint test
#: needs; a compare/align journey needs two genuinely different records, so
#: this module carries its own two-accession handler instead.
SECOND_ACCESSION = "NM_000002.1"

#: 12 bp, the same sequence ``conftest.NCBI_TEST_SEQUENCE`` pins.
FIRST_SEQUENCE = "ACGTACGTACGT"
#: 10 bp: the first sequence minus two 3' bases, so a comparison against it
#: has unequal lengths (Hamming/identity undefined) and a known edit distance.
SECOND_SEQUENCE = "ACGTACGTAC"

#: Free-text query the stub resolves to the first record.
SEARCH_TERM = "test"

_UID_BY_ACCESSION = {NCBI_TEST_ACCESSION: "111", SECOND_ACCESSION: "222"}
_SEQUENCE_BY_UID = {"111": FIRST_SEQUENCE, "222": SECOND_SEQUENCE}


def _ncbi_handler(request: httpx.Request) -> httpx.Response:
    """A two-accession E-utilities stub.

    Resolves the search term and the two known accessions; any other term
    reports zero hits, which is how the client turns an unknown accession
    into a 404.
    """
    path = request.url.path
    params = request.url.params
    if path.endswith("esearch.fcgi"):
        term = params.get("term")
        if term == SEARCH_TERM:
            uids = ["111"]
        elif term in _UID_BY_ACCESSION:
            uids = [_UID_BY_ACCESSION[term]]
        else:
            uids = []
        return httpx.Response(
            200,
            json={
                "esearchresult": {
                    "count": str(len(uids)),
                    "retmax": str(len(uids)),
                    "retstart": "0",
                    "idlist": uids,
                }
            },
        )
    if path.endswith("esummary.fcgi"):
        requested = params.get("id", "").split(",")
        entries = {
            uid: {
                "uid": uid,
                "caption": accession,
                "slen": len(_SEQUENCE_BY_UID[uid]),
                "title": f"synthetic {accession}",
            }
            for accession, uid in _UID_BY_ACCESSION.items()
            if uid in requested
        }
        return httpx.Response(200, json={"result": {"uids": list(entries), **entries}})
    if path.endswith("efetch.fcgi"):
        uid = params.get("id", "")
        accession = next(a for a, u in _UID_BY_ACCESSION.items() if u == uid)
        sequence = _SEQUENCE_BY_UID[uid]
        return httpx.Response(
            200, text=f">{accession} synthetic {accession}\n{sequence}\n"
        )
    raise AssertionError(f"unexpected NCBI request: {request.url}")


def _app_client(
    *,
    ena_handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> httpx.AsyncClient:
    """Build one app with mocked provider clients and return a client for it.

    Unlike the route tests there is a single app per test, shared by every
    step of the journey — that is what makes the flow end to end.
    """
    databases: dict[str, SequenceDatabase] = {
        "ncbi": NCBISequenceDatabase(
            email="test@example.com",
            transport=httpx.MockTransport(_ncbi_handler),
            max_retries=0,
        )
    }
    if ena_handler is not None:
        databases["ena"] = ENASequenceDatabase(
            transport=httpx.MockTransport(ena_handler), max_retries=0
        )
    app = create_app(databases=databases)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


def _md5(sequence: str) -> str:
    return hashlib.md5(sequence.encode("utf-8"), usedforsecurity=False).hexdigest()


async def test_search_fetch_analyse_compare_align_export_journey() -> None:
    """The full NCBI journey, asserting the endpoints agree throughout."""
    async with _app_client() as client:
        # 1. The advertised database list.
        databases = (await client.get("/api/databases")).json()["databases"]
        assert {entry["name"] for entry in databases} == {"ncbi", "ena"}

        # 2. Search finds the first synthetic record.
        search = (
            await client.get(
                "/api/databases/ncbi/search", params={"query": SEARCH_TERM}
            )
        ).json()
        assert [hit["accession"] for hit in search["results"]] == [NCBI_TEST_ACCESSION]

        # 3. Fetching it yields the sequence the rest of the journey analyses.
        record = (
            await client.get(f"/api/databases/ncbi/sequences/{NCBI_TEST_ACCESSION}")
        ).json()
        assert record["sequence"] == FIRST_SEQUENCE
        assert record["length"] == len(FIRST_SEQUENCE)

        # 4. Statistics for that same record.
        statistics = (
            await client.get(
                f"/api/sequences/{NCBI_TEST_ACCESSION}/statistics",
                params={"database": "ncbi"},
            )
        ).json()
        assert statistics["length"] == record["length"] == len(FIRST_SEQUENCE)
        assert statistics["gc_content"] == 50.0  # ACGT repeated: 6 G/C of 12

        # 5. QC verdict for that same record (12 bp is below the 100 bp floor).
        quality = (
            await client.get(
                f"/api/sequences/{NCBI_TEST_ACCESSION}/quality",
                params={"database": "ncbi"},
            )
        ).json()
        assert quality["passed"] is False
        assert quality["min_length"] > len(FIRST_SEQUENCE)

        # 6a. Compare the record against itself.
        same = (
            await client.get(
                "/api/compare", params={"accession_a": NCBI_TEST_ACCESSION}
            )
        ).json()
        assert same["hamming_distance"] == 0
        assert same["percent_identity"] == 100.0

        # 6b. Compare it against the shorter record: the equal-length metrics
        # are undefined (null), not silently zero, while edit distance works.
        shorter = (
            await client.get(
                "/api/compare",
                params={
                    "accession_a": NCBI_TEST_ACCESSION,
                    "accession_b": SECOND_ACCESSION,
                },
            )
        ).json()
        assert (shorter["length_a"], shorter["length_b"]) == (
            len(FIRST_SEQUENCE),
            len(SECOND_SEQUENCE),
        )
        assert shorter["hamming_distance"] is None
        assert shorter["percent_identity"] is None
        assert shorter["levenshtein_distance"] == 2  # two deleted 3' bases

        # 7. Align the record against itself: 12 matches at match_score 1.0.
        alignment = (
            await client.get("/api/align", params={"accession_a": NCBI_TEST_ACCESSION})
        ).json()
        assert alignment["score"] == float(len(FIRST_SEQUENCE))
        assert alignment["aligned_a"] == alignment["aligned_b"] == FIRST_SEQUENCE
        assert alignment["mode"] == "global"

        # 8. Export the sequence and check the document against the endpoints
        # that produced its parts: the same record projection, the same
        # statistics, the same QC report, and provenance over that sequence.
        export = (
            await client.get(
                f"/api/export/sequence/{NCBI_TEST_ACCESSION}/json",
                params={"database": "ncbi"},
            )
        ).json()
        assert export["record"] == record
        assert export["statistics"] == statistics
        assert export["quality"] == quality

        source = export["provenance"]["sources"][0]
        assert source["accession"] == NCBI_TEST_ACCESSION
        assert source["source_database"] == "ncbi"
        assert source["length"] == record["length"]
        assert source["md5"] == _md5(record["sequence"])
        assert source["metadata"] == record["metadata"]
        assert export["provenance"]["parameters"] == {}


async def test_ena_journey_keeps_the_raw_payload_in_provenance_only(
    ena_happy_path_handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """An ENA journey: the raw provider text survives, but only in provenance."""
    async with _app_client(ena_handler=ena_happy_path_handler) as client:
        search = (
            await client.get("/api/databases/ena/search", params={"query": "test"})
        ).json()
        assert ENA_TEST_ACCESSION in [hit["accession"] for hit in search["results"]]

        record = (
            await client.get(f"/api/databases/ena/sequences/{ENA_TEST_ACCESSION}")
        ).json()
        assert record["source_database"] == "ena"
        # The compact projection carries no raw payload (Stage 9 denylist).
        assert record["metadata"] == {}

        statistics = (
            await client.get(
                f"/api/sequences/{ENA_TEST_ACCESSION}/statistics",
                params={"database": "ena"},
            )
        ).json()
        assert statistics["accession"] == ENA_TEST_ACCESSION

        export = (
            await client.get(
                f"/api/export/sequence/{ENA_TEST_ACCESSION}/json",
                params={"database": "ena"},
            )
        ).json()
        # Same projection as the read endpoint...
        assert export["record"] == record
        assert export["statistics"] == statistics
        # ...while the provenance block does carry the raw ENA response.
        source = export["provenance"]["sources"][0]
        assert source["metadata"]["ena_fasta_raw"] == ENA_TEST_FASTA
        assert str(source["metadata"]["ena_request_url"]).endswith(
            f"/fasta/{ENA_TEST_ACCESSION}"
        )
        assert source["md5"] == _md5(record["sequence"])


async def test_compare_and_align_exports_match_their_read_endpoints() -> None:
    """Both formats of both exports restate the read endpoint byte for byte."""
    params: dict[str, str | int] = {
        "accession_a": NCBI_TEST_ACCESSION,
        "accession_b": SECOND_ACCESSION,
        "database": "ncbi",
    }
    async with _app_client() as client:
        comparison = (await client.get("/api/compare", params=params)).json()
        comparison_export = (
            await client.get("/api/export/compare/json", params=params)
        ).json()
        assert comparison_export["comparison"] == comparison
        assert comparison_export["provenance"]["parameters"] == {"k": 4}
        assert [
            source["accession"] for source in comparison_export["provenance"]["sources"]
        ] == [NCBI_TEST_ACCESSION, SECOND_ACCESSION]

        align_params: dict[str, str | int | float] = {
            **params,
            "mode": "local",
            "open_gap_score": -3,
        }
        alignment = (await client.get("/api/align", params=align_params)).json()
        alignment_export = (
            await client.get("/api/export/align/json", params=align_params)
        ).json()
        assert alignment_export["alignment"] == alignment
        assert alignment_export["provenance"]["parameters"]["mode"] == "local"
        assert alignment_export["provenance"]["parameters"]["open_gap_score"] == -3.0

        text = (await client.get("/api/export/align/text", params=align_params)).text
        assert text.startswith("# sequence-platform pairwise alignment export")
        assert f"# mode: local, score: {alignment['score']}" in text
        assert f"# columns: {len(alignment['aligned_a'])}" in text
        assert alignment["aligned_a"] in text
        assert alignment["aligned_b"] in text
        # One line covers every alignment column with the match/mismatch/gap
        # characters only — the same column kinds the Stage 8.5 view colours.
        match_lines = [
            line.strip()
            for line in text.splitlines()
            if len(line.strip()) == len(alignment["aligned_a"])
            and set(line.strip()) <= {"|", ".", " "}
        ]
        assert len(match_lines) == 1
        assert len(match_lines[0]) == len(alignment["aligned_a"])


async def test_error_mapping_is_the_same_across_route_families() -> None:
    """One handler stack serves the read, analysis and export routes alike."""
    async with _app_client() as client:
        unknown = "NOT_A_REAL_ACCESSION"

        # An unknown accession is a 404 with a JSON body on every route that
        # fetches a record — including both sides of the Stage 9 extraction.
        for url, params in (
            (f"/api/databases/ncbi/sequences/{unknown}", None),
            (f"/api/sequences/{unknown}/statistics", {"database": "ncbi"}),
            (f"/api/sequences/{unknown}/quality", {"database": "ncbi"}),
            (f"/api/export/sequence/{unknown}/json", {"database": "ncbi"}),
            ("/api/compare", {"accession_a": unknown}),
            ("/api/align", {"accession_a": unknown}),
        ):
            response = await client.get(url, params=params)
            assert response.status_code == 404, url
            assert "detail" in response.json(), url
            assert "Traceback" not in response.text, url

        # An unregistered database is a 404 as well, on both families.
        assert (
            await client.get(f"/api/databases/ena/sequences/{NCBI_TEST_ACCESSION}")
        ).status_code == 404
        assert (
            await client.get(
                f"/api/export/sequence/{NCBI_TEST_ACCESSION}/json",
                params={"database": "ena"},
            )
        ).status_code == 404
