---
name: scientific-testing
description: Write or review unit tests for scientific/biological calculations in this project - GC content, composition, identity, distance, alignment scoring, quality-control metrics. Use whenever adding tests for anything in analysis/, when the user asks for test coverage, or when reviewing whether a scientific calculation is adequately tested.
---

# Scientific Testing

How to test scientific calculations in this codebase so results are trustworthy, not just "code runs without crashing."

## Core Principle
A scientific test is not complete if it only asserts "no exception was raised." Prefer tests with a hand-computed or externally-verifiable expected value.

## Known-Answer Tests
For every calculation function, include at least one test using a small, hand-verifiable sequence:
- Example: a designed 20-40bp sequence where GC content, base counts, and reverse complement can be computed by hand and hard-coded as the expected value in the test.
- Where a published/reference tool result is available (e.g. a known EMBOSS or Biopython output for a public test sequence), cite where the expected value came from in a test comment.

## Determinism
- Scientific calculation functions must produce identical output on repeated runs with the same input. If a function has any randomness (e.g. Monte Carlo QC sampling), the test must fix the random seed explicitly and assert on the seeded result.
- Do not use `time.time()`, unseeded `random`, or wall-clock-dependent behavior inside anything being unit tested for a numeric result.

## Mandatory Edge Cases
For each category of calculation, test:
- **Composition/GC content**: empty sequence, all-N sequence, mixed-case sequence, single base.
- **Identity/distance**: equal-length sequences, different-length sequences (should raise or require alignment - confirm which), fully identical sequences (100% identity / 0 distance), fully divergent sequences.
- **Alignment**: empty sequence input, one empty + one non-empty sequence, identical sequences, sequences with no similarity.
- **Ambiguous bases**: sequences containing IUPAC ambiguity codes should not silently be treated as invalid or as a specific base - assert the actual documented behavior.
- **Invalid input**: sequence containing characters outside IUPAC nucleotide codes should raise a clear exception, not be silently accepted.

## Fixtures & Mocks
- Reference sequences used across multiple tests belong in a shared `conftest.py` fixture, not copy-pasted into each test file.
- Any test that would otherwise need real network access (database client tests) must use a fixture/mock (`responses` library, saved JSON/FASTA fixture files under `tests/fixtures/`) - real API calls are never allowed inside the automated test suite.

## Regression Tests
- When a bug is found in a scientific calculation, add a regression test reproducing the exact failing input/output before fixing the bug, so the fix is verified and the bug cannot silently return.

## Test Organization
- Mirror the `analysis/` module structure in `tests/`: `analysis/composition/` -> `tests/analysis/composition/`, etc., so it's obvious which tests cover which module.
- Name tests descriptively: `test_gc_content_handles_empty_sequence`, not `test_gc_1`.
