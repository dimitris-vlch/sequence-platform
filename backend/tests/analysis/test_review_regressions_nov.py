"""Regression tests for bugs found in the November 2026 code review."""

from __future__ import annotations

import math
import random

import httpx
import pytest
from fastapi import FastAPI

from sequence_platform.analysis.alignment import global_alignment, local_alignment
from sequence_platform.analysis.distance import (
    hamming_distance,
    levenshtein_distance,
    percent_identity,
)
from sequence_platform.analysis.similarity import compare, jaccard_kmer_similarity
from sequence_platform.database.base import SequenceDatabase, SequenceSummary
from sequence_platform.database.ena.client import ENASequenceDatabase
from sequence_platform.main import create_app
from sequence_platform.models import SeqType, SequenceRecord

# --- Alignment scores -------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["match_score", "mismatch_score", "open_gap_score", "extend_gap_score"]
)
@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_alignment_rejects_non_finite_scores(field: str, value: float) -> None:
    # An infinite gap score used to segfault Biopython's C aligner, killing
    # the whole server process.
    with pytest.raises(ValueError, match="finite"):
        global_alignment("ACGT", "ACGA", **{field: value})


@pytest.mark.parametrize("field", ["open_gap_score", "extend_gap_score"])
def test_alignment_rejects_positive_gap_scores(field: str) -> None:
    with pytest.raises(ValueError, match="<= 0"):
        global_alignment("ACGT", "ACGA", **{field: 1.0})


def test_local_alignment_without_positive_pair_is_empty() -> None:
    result = local_alignment("AAAA", "TTTT")
    assert result.score == 0.0
    assert (result.aligned_a, result.aligned_b) == ("", "")
    assert (result.start_a, result.end_a, result.start_b, result.end_b) == (0, 0, 0, 0)


def test_alignment_pairs_t_with_u_across_dna_and_rna() -> None:
    dna = SequenceRecord("d", "ACGTTT")
    rna = SequenceRecord("r", "ACGUUU", seq_type=SeqType.RNA)
    result = global_alignment(dna, rna)
    assert result.score == 6.0
    assert result.aligned_a == result.aligned_b == "ACGTTT"


# --- Distance / similarity --------------------------------------------------


def test_dna_and_rna_counterparts_compare_identical() -> None:
    dna = SequenceRecord("d", "ACGTTTACGT")
    rna = SequenceRecord("r", "ACGUUUACGU", seq_type=SeqType.RNA)
    assert hamming_distance(dna, rna) == 0
    assert percent_identity(dna, rna) == 100.0
    assert levenshtein_distance(dna, rna) == 0
    assert jaccard_kmer_similarity(dna, rna, k=3) == 100.0
    assert compare(dna, rna, k=3).normalized_edit_similarity == 100.0


def _reference_levenshtein(a: str, b: str) -> int:
    """The textbook dynamic programme the C-backed version replaced."""
    prev = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        row = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            if char_a == b[j - 1]:
                row[j] = prev[j - 1]
            else:
                row[j] = 1 + min(prev[j], row[j - 1], prev[j - 1])
        prev = row
    return prev[-1]


def test_levenshtein_matches_textbook_dynamic_programme() -> None:
    rnd = random.Random(20261109)
    for _ in range(500):
        a = "".join(rnd.choice("ACGTN") for _ in range(rnd.randint(0, 25)))
        b = "".join(rnd.choice("ACGTN") for _ in range(rnd.randint(0, 25)))
        assert levenshtein_distance(a, b) == _reference_levenshtein(a, b)


def test_compare_handles_multi_kilobase_sequences() -> None:
    # The former pure-Python cap (10M cells) rejected anything over ~3.2 kb,
    # even comparing a record with itself.
    rnd = random.Random(7)
    sequence = "".join(rnd.choice("ACGT") for _ in range(8000))
    report = compare(sequence, sequence)
    assert report.levenshtein_distance == 0
    assert report.normalized_edit_similarity == 100.0


# --- ENA accession ------------------------------------------------------------


async def test_ena_fetch_strips_pipe_delimited_header() -> None:
    # The real ENA /fasta payload; the whole "ENA|...|..." token used to
    # become the accession, which ENA answers with 400 when exports refetch it.
    fasta = ">ENA|MN908947|MN908947.3 Severe acute respiratory syndrome\nACGTACGT\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=fasta)

    client = ENASequenceDatabase(transport=httpx.MockTransport(handler), max_retries=0)
    try:
        record = await client.fetch("MN908947")
    finally:
        await client.close()
    assert record.accession == "MN908947.3"
    assert record.description == "Severe acute respiratory syndrome"
    assert record.to_fasta().startswith(">MN908947.3 Severe acute")


# --- HTTP layer ---------------------------------------------------------------


class _FakeDatabase(SequenceDatabase):
    name = "ncbi"
    _records = {"A": "AAAA", "T": "TTTT"}

    async def fetch(self, accession: str) -> SequenceRecord:
        return SequenceRecord(accession, self._records[accession])

    async def search(
        self, query: str, *, max_results: int = 20
    ) -> list[SequenceSummary]:
        return []


def _http_client() -> httpx.AsyncClient:
    application: FastAPI = create_app(databases={"ncbi": _FakeDatabase()})
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/align?accession_a=A&accession_b=T&open_gap_score=inf",
        "/api/align?accession_a=A&accession_b=T&match_score=nan",
        "/api/export/align/json?accession_a=A&accession_b=T&extend_gap_score=-inf",
        "/api/export/align/text?accession_a=A&accession_b=T&open_gap_score=1",
    ],
)
async def test_invalid_scores_are_rejected_with_422(path: str) -> None:
    async with _http_client() as client:
        response = await client.get(path)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/api/align?accession_a=A&accession_b=T&mode=local",
        "/api/export/align/text?accession_a=A&accession_b=T&mode=local",
    ],
)
async def test_local_alignment_without_match_is_not_a_server_error(path: str) -> None:
    async with _http_client() as client:
        response = await client.get(path)
    assert response.status_code == 200
