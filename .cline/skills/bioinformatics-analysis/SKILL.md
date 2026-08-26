---
name: bioinformatics-analysis
description: Implement or review nucleotide sequence analysis code - GC content, composition, ambiguous base detection, reverse complement, sequence identity, distance metrics, alignment. Use when writing or editing anything in analysis/composition, analysis/statistics, analysis/similarity, analysis/alignment, or when the user mentions FASTA/GenBank parsing, GC content, nucleotide composition, IUPAC ambiguity codes, reverse complement, pairwise identity, or sequence distance.
---

# Bioinformatics Analysis

Guidance for implementing scientifically correct nucleotide sequence analysis using Biopython.

## Core Rules
- Analysis functions must be pure and deterministic: same input -> same output, no hidden randomness, no network calls inside analysis code.
- Never invent or approximate a biological result. If a calculation cannot be performed (e.g. empty sequence for GC content), raise a clear, typed exception - do not return 0 or None silently.
- Keep analysis code independent from database/retrieval code. Analysis functions take a `Seq` (or plain str) and return typed results, never an accession or API response object.

## Biopython Conventions
- Use `Bio.Seq.Seq` for sequence objects, not raw strings, once past the parsing boundary.
- Use `Bio.SeqIO` for FASTA/GenBank parsing (`SeqIO.parse` for multi-record, `SeqIO.read` for single-record - `SeqIO.read` raises if the file doesn't contain exactly one record, which is usually what you want for validation).
- Preserve `SeqRecord.id`, `.description`, and `.annotations` (GenBank) when round-tripping - do not silently drop metadata during parse/export.

## Nucleotide Composition & GC Content
- GC content = (count(G) + count(C)) / total_length * 100, counted over standard bases only unless explicitly asked to include ambiguous bases in the denominator - state which convention you used in a docstring.
- IUPAC ambiguous bases (N, R, Y, S, W, K, M, B, D, H, V) must be detected and reported separately, never silently treated as A/T/G/C.
- Composition functions must handle mixed-case input (some FASTA files use lowercase for masked/repeat regions) - normalize case before counting, but note in output if the sequence was mixed-case.

## Reverse Complement
- Use Biopython's built-in `Seq.reverse_complement()` rather than hand-rolling it, so ambiguous base complementation (IUPAC pairing table) is handled correctly.
- Ambiguous bases have defined complements (e.g. N->N, R<->Y) - verify Biopython's table is being used, don't assume only ACGT.

## Sequence Identity & Distance
- Define "identity" precisely before implementing: ungapped percent identity over aligned positions is different from identity over the shorter sequence's length. Document which definition is used.
- For sequences of different lengths, either require alignment first or explicitly define the comparison method (e.g. global alignment, then compute identity over alignment columns). Never silently truncate to the shorter sequence without flagging this in the result.
- Distance metrics (Hamming, edit distance) must state their assumptions: Hamming distance requires equal-length sequences - raise an error if lengths differ, don't pad silently.

## Alignment
- Use Biopython's `Bio.Align.PairwiseAligner` for pairwise alignment rather than reimplementing Needleman-Wunsch/Smith-Waterman from scratch, unless there's a specific reason documented.
- Make scoring parameters (match/mismatch/gap open/gap extend) explicit and configurable, not hardcoded magic numbers buried in the function body.

## Mandatory Edge Cases to Test
Every analysis function needs tests covering:
- Empty sequence (`""` or zero-length `Seq`)
- Sequence containing only ambiguous bases (e.g. all `N`)
- Sequence with mixed case
- Sequences of different lengths (for identity/distance functions)
- Single-base sequence
- Sequence with non-IUPAC characters (invalid input) - should raise, not silently ignore

## Known-Answer Tests
Wherever possible, use a reference sequence with a hand-verified expected result (e.g. a short designed sequence where GC content, reverse complement, and composition can be checked by hand) rather than only asserting the function runs without error.
