"""HTTP-layer tests for the Stage 9 export routes.

Same conventions as ``test_databases.py``: the app is built in-process with
mocked clients injected into ``create_app`` and driven through
``httpx.ASGITransport`` — no network, no real external request (§2).
"""

from __future__ import annotations

import hashlib

import httpx

from conftest import (
    ENA_TEST_ACCESSION,
    ENA_TEST_DESCRIPTION,
    ENA_TEST_FASTA,
    ENA_TEST_SEQUENCE,
    NCBI_TEST_ACCESSION,
    NCBI_TEST_ESUMMARY_ENTRY,
    NCBI_TEST_FASTA,
    NCBI_TEST_SEQUENCE,
)
from sequence_platform.analysis import quality_control
from sequence_platform.api.export import alignment_text, match_line, safe_filename
from sequence_platform.api.schemas import AlignmentResponse
from sequence_platform.database.base import SequenceDatabase
from sequence_platform.database.ena.client import ENASequenceDatabase
from sequence_platform.database.ncbi.client import NCBISequenceDatabase
from sequence_platform.main import create_app


def _client(
    ncbi_transport: httpx.MockTransport,
    ena_transport: httpx.MockTransport | None = None,
) -> httpx.AsyncClient:
    """Build an in-process client with mocked provider clients injected."""
    databases: dict[str, SequenceDatabase] = {
        "ncbi": NCBISequenceDatabase(
            email="test@example.com", transport=ncbi_transport, max_retries=0
        )
    }
    if ena_transport is not None:
        databases["ena"] = ENASequenceDatabase(transport=ena_transport, max_retries=0)
    app = create_app(databases=databases)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


async def test_export_sequence_fasta_round_trips_the_provider_fasta(
    ncbi_transport: httpx.MockTransport,
) -> None:
    """The platform's own FASTA writer re-emits the retrieved document."""
    async with _client(ncbi_transport) as client:
        response = await client.get(
            f"/api/export/sequence/{NCBI_TEST_ACCESSION}/fasta",
            params={"database": "ncbi"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/x-fasta")
    assert response.text == NCBI_TEST_FASTA
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="{NCBI_TEST_ACCESSION}.fasta"'
    )


async def test_export_sequence_fasta_ena(
    ncbi_transport: httpx.MockTransport,
    ena_transport: httpx.MockTransport,
) -> None:
    async with _client(ncbi_transport, ena_transport) as client:
        response = await client.get(
            f"/api/export/sequence/{ENA_TEST_ACCESSION}/fasta",
            params={"database": "ena"},
        )
    assert response.status_code == 200
    assert response.text == ENA_TEST_FASTA


async def test_export_sequence_json_carries_record_statistics_quality_provenance(
    ncbi_transport: httpx.MockTransport,
) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get(
            f"/api/export/sequence/{NCBI_TEST_ACCESSION}/json",
            params={"database": "ncbi"},
        )
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{NCBI_TEST_ACCESSION}.json"'
    )
    body = response.json()

    provenance = body["provenance"]
    assert provenance["application"] == "sequence-platform"
    assert provenance["version"] != ""
    assert provenance["generated_at"].endswith("+00:00")
    assert provenance["parameters"] == {}

    source = provenance["sources"][0]
    assert source["accession"] == NCBI_TEST_ACCESSION
    assert source["source_database"] == "ncbi"
    assert source["length"] == len(NCBI_TEST_SEQUENCE)
    expected_md5 = hashlib.md5(
        NCBI_TEST_SEQUENCE.encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    assert source["md5"] == expected_md5
    assert source["metadata"] == {"ncbi_esummary": NCBI_TEST_ESUMMARY_ENTRY}

    # The record, statistics, and QC report mirror their own endpoints.
    assert body["record"]["sequence"] == NCBI_TEST_SEQUENCE
    assert body["statistics"]["gc_content"] == 50.0
    assert body["statistics"]["length"] == len(NCBI_TEST_SEQUENCE)
    assert body["quality"]["passed"] is False
    assert body["quality"]["min_length"] == quality_control.DEFAULT_MIN_LENGTH
    assert body["quality"]["max_n_run"] == quality_control.DEFAULT_MAX_N_RUN


async def test_export_sequence_json_ena_retains_the_raw_provider_payload(
    ncbi_transport: httpx.MockTransport,
    ena_transport: httpx.MockTransport,
) -> None:
    """Stage 9/Part B payoff: the raw ENA response is part of the provenance."""
    async with _client(ncbi_transport, ena_transport) as client:
        response = await client.get(
            f"/api/export/sequence/{ENA_TEST_ACCESSION}/json",
            params={"database": "ena"},
        )
    assert response.status_code == 200
    source = response.json()["provenance"]["sources"][0]
    assert source["source_database"] == "ena"
    assert source["metadata"]["ena_fasta_raw"] == ENA_TEST_FASTA
    assert str(source["metadata"]["ena_request_url"]).endswith(
        f"/fasta/{ENA_TEST_ACCESSION}"
    )
    body = response.json()
    assert body["record"]["description"] == ENA_TEST_DESCRIPTION
    assert body["record"]["sequence"] == ENA_TEST_SEQUENCE
    # The record sub-object is the compact projection, so the raw payload
    # appears exactly once in this document — in the provenance block above.
    assert body["record"]["metadata"] == {}
    expected_md5 = hashlib.md5(
        ENA_TEST_SEQUENCE.encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    assert source["md5"] == expected_md5


async def test_export_sequence_unknown_accession_returns_404(
    ncbi_not_found_transport: httpx.MockTransport,
) -> None:
    async with _client(ncbi_not_found_transport) as client:
        response = await client.get(
            "/api/export/sequence/does-not-exist/json", params={"database": "ncbi"}
        )
    assert response.status_code == 404
    assert "detail" in response.json()


async def test_export_sequence_unknown_database_returns_404(
    ncbi_transport: httpx.MockTransport,
) -> None:
    """``ena`` is advertised, but no client is injected into this app."""
    async with _client(ncbi_transport) as client:
        response = await client.get(
            f"/api/export/sequence/{NCBI_TEST_ACCESSION}/json",
            params={"database": "ena"},
        )
    assert response.status_code == 404


async def test_export_compare_json_carries_metrics_and_parameters(
    ncbi_transport: httpx.MockTransport,
) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get(
            "/api/export/compare/json",
            params={
                "accession_a": NCBI_TEST_ACCESSION,
                "accession_b": NCBI_TEST_ACCESSION,
                "database": "ncbi",
                "k": 4,
            },
        )
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")
    body = response.json()
    assert body["comparison"]["percent_identity"] == 100.0
    assert body["comparison"]["levenshtein_distance"] == 0
    assert body["comparison"]["k"] == 4
    # One provenance entry per input record, plus the analysis parameters.
    assert [source["accession"] for source in body["provenance"]["sources"]] == [
        NCBI_TEST_ACCESSION,
        NCBI_TEST_ACCESSION,
    ]
    assert body["provenance"]["parameters"] == {"k": 4}


async def test_export_compare_json_defaults_to_ncbi(
    ncbi_transport: httpx.MockTransport,
) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get(
            "/api/export/compare/json",
            params={"accession_a": NCBI_TEST_ACCESSION},
        )
    assert response.status_code == 200
    assert response.json()["provenance"]["sources"][0]["source_database"] == "ncbi"


async def test_export_align_json_carries_result_and_parameters(
    ncbi_transport: httpx.MockTransport,
) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get(
            "/api/export/align/json",
            params={
                "accession_a": NCBI_TEST_ACCESSION,
                "database": "ncbi",
                "mode": "local",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["alignment"]["mode"] == "local"
    assert body["alignment"]["score"] == 12.0
    assert body["alignment"]["aligned_a"] == NCBI_TEST_SEQUENCE
    assert body["provenance"]["parameters"]["mode"] == "local"
    assert body["provenance"]["parameters"]["open_gap_score"] == -2.0


async def test_export_align_text_contains_both_rows_and_the_match_line(
    ncbi_transport: httpx.MockTransport,
) -> None:
    async with _client(ncbi_transport) as client:
        response = await client.get(
            "/api/export/align/text",
            params={"accession_a": NCBI_TEST_ACCESSION, "database": "ncbi"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["content-disposition"].endswith('-global.txt"')
    text = response.text
    assert f"# mode: global, score: {float(len(NCBI_TEST_SEQUENCE))}" in text
    assert NCBI_TEST_SEQUENCE in text
    # Identical sequences: an all-match line as long as the alignment.
    assert "|" * len(NCBI_TEST_SEQUENCE) in text


def test_match_line_marks_matches_mismatches_and_gaps() -> None:
    """6 matches, 1 mismatch, 1 gap — one character per alignment column."""
    assert match_line("ACGTACGT", "ACGAAC-T") == "|||.|| |"
    # A length disagreement pads rather than dropping columns.
    assert match_line("ACGT", "AC") == "||  "


def test_alignment_text_reports_counts_and_both_rows() -> None:
    response = AlignmentResponse(
        accession_a="A_1",
        accession_b="B_1",
        mode="global",
        score=3.0,
        aligned_a="ACGTACGT",
        aligned_b="ACGAAC-T",
        start_a=0,
        end_a=8,
        start_b=0,
        end_b=8,
        match_score=1.0,
        mismatch_score=-1.0,
        open_gap_score=-2.0,
        extend_gap_score=-0.5,
    )
    text = alignment_text(response)
    assert "# mode: global, score: 3.0" in text
    assert "# columns: 8 (matches 6, mismatches 1, gaps 1)" in text
    assert "A_1 ACGTACGT" in text
    assert "B_1 ACGAAC-T" in text
    assert "|||.|| |" in text


def test_safe_filename_strips_header_unsafe_characters() -> None:
    assert safe_filename("NM_000001.1", ".fasta") == "NM_000001.1.fasta"
    assert safe_filename("A_1-vs-B_2", ".json") == "A_1-vs-B_2.json"
    # Path separators, quotes, CR/LF (header injection) and an empty stem.
    assert safe_filename('bad/name"\r\n', ".json") == "bad_name.json"
    assert safe_filename("", ".json") == "export.json"
