"""Known-answer tests for the pure Stage 5 similarity functions.

Values are hand-computed; the edit-similarity and k-mer Jaccard formulas are
the documented Stage 5 rules, and ``compare`` must aggregate them (returning
``None`` for the equal-length-only metrics when the inputs differ in length).
"""

import pytest

from sequence_platform.analysis.similarity import (
    ComparisonReport,
    compare,
    jaccard_kmer_similarity,
    normalized_edit_similarity,
)

# --- normalized_edit_similarity -------------------------------------------


def test_edit_similarity_identical_is_hundred():
    assert normalized_edit_similarity("ACGT", "ACGT") == 100.0


def test_edit_similarity_one_substitution_over_four():
    assert normalized_edit_similarity("ACGT", "ATGT") == pytest.approx(75.0)


def test_edit_similarity_unequal_length_uses_max():
    assert normalized_edit_similarity("ACG", "ACGT") == pytest.approx(75.0)
    assert normalized_edit_similarity("ACGT", "ACG") == pytest.approx(75.0)


def test_edit_similarity_completely_different():
    # ACGT vs TAGC has edit distance 3, max length 4 -> 25.0.
    assert normalized_edit_similarity("ACGT", "TAGC") == pytest.approx(25.0)


def test_edit_similarity_two_empty_is_hundred():
    assert normalized_edit_similarity("", "") == 100.0


def test_edit_similarity_one_empty_is_zero():
    assert normalized_edit_similarity("AC", "") == 0.0


# --- jaccard_kmer_similarity ----------------------------------------------


def test_jaccard_identical_is_hundred():
    assert jaccard_kmer_similarity("ACGT", "ACGT", k=2) == 100.0


def test_jaccard_partial_overlap():
    # {AC, CG, GT} vs {AC, CG, GA}: intersection {AC, CG}, union of 4.
    assert jaccard_kmer_similarity("ACGT", "ACGA", k=2) == pytest.approx(50.0)


def test_jaccard_disjoint_is_zero():
    # {AC, CG, GT} vs {TG, GC, CA}: no shared k-mers.
    assert jaccard_kmer_similarity("ACGT", "TGCA", k=2) == 0.0


def test_jaccard_both_empty_is_hundred():
    assert jaccard_kmer_similarity("", "", k=4) == 100.0


def test_jaccard_one_empty_is_zero():
    assert jaccard_kmer_similarity("ACGT", "", k=4) == 0.0
    assert jaccard_kmer_similarity("", "ACGT", k=4) == 0.0


def test_jaccard_k_too_large_raises():
    with pytest.raises(ValueError):
        jaccard_kmer_similarity("AC", "ACGT", k=4)


def test_jaccard_k_below_one_raises():
    with pytest.raises(ValueError):
        jaccard_kmer_similarity("ACGT", "ACGT", k=0)


# --- compare --------------------------------------------------------------


def test_compare_equal_length_aggregates_all_metrics():
    report = compare("ACGT", "ATGT", k=2)
    assert isinstance(report, ComparisonReport)
    assert report.length_a == 4
    assert report.length_b == 4
    assert report.hamming_distance == 1
    assert report.percent_identity == pytest.approx(75.0)
    assert report.levenshtein_distance == 1
    assert report.normalized_edit_similarity == pytest.approx(75.0)
    # {AC, CG, GT} vs {AT, TG, GT}: intersection {GT}, union of 5.
    assert report.jaccard_kmer_similarity == pytest.approx(20.0)


def test_compare_unequal_length_nulls_positional_metrics():
    report = compare("AC", "ATG", k=2)
    assert report.length_a == 2
    assert report.length_b == 3
    assert report.hamming_distance is None
    assert report.percent_identity is None
    assert report.levenshtein_distance == 2
    assert report.normalized_edit_similarity == pytest.approx(33.33)
    # {AC} vs {AT, TG}: no shared k-mers.
    assert report.jaccard_kmer_similarity == 0.0


def test_compare_identical_is_all_maximal():
    report = compare("ACGT", "ACGT", k=4)
    assert report.hamming_distance == 0
    assert report.percent_identity == 100.0
    assert report.levenshtein_distance == 0
    assert report.normalized_edit_similarity == 100.0
    assert report.jaccard_kmer_similarity == 100.0
