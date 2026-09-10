import { useState, type FormEvent, type ReactNode } from "react";

import {
  alignSequences,
  alignmentJsonExportUrl,
  alignmentTextExportUrl,
  errorMessage,
  type AlignParams,
  type AlignmentMode,
  type AlignmentResponse,
} from "../api/client";
import { DatabaseSelector } from "./DatabaseSelector";

export interface AlignmentViewProps {
  /** Database selected when the view first renders. */
  initialDatabase?: string;
}

/**
 * Gap character used in the backend's aligned strings
 * (`analysis/alignment/base.py`: `aligned_a = str(best[0])`). There is no
 * CIGAR string in `AlignmentResponse`, so the per-column
 * match/mismatch/gap classification is derived from the two gapped strings.
 */
const GAP = "-";

/**
 * One `<span>` per alignment column is DOM-heavy on long sequences, so only
 * the first N columns are rendered — and the panel says so, rather than
 * truncating silently.
 */
const MAX_RENDERED_COLUMNS = 400;

interface ColumnCounts {
  columns: number;
  matches: number;
  mismatches: number;
  gaps: number;
}

/** Count match / mismatch / gap columns directly from the aligned strings. */
function countColumns(alignedA: string, alignedB: string): ColumnCounts {
  const columns = Math.max(alignedA.length, alignedB.length);
  let matches = 0;
  let mismatches = 0;
  let gaps = 0;
  for (let index = 0; index < columns; index += 1) {
    const a = alignedA[index] ?? GAP;
    const b = alignedB[index] ?? GAP;
    if (a === GAP || b === GAP) {
      gaps += 1;
    } else if (a === b) {
      matches += 1;
    } else {
      mismatches += 1;
    }
  }
  return { columns, matches, mismatches, gaps };
}

/** CSS class distinguishing the three column kinds. */
function columnClass(a: string, b: string): string {
  if (a === GAP || b === GAP) {
    return "col-gap";
  }
  return a === b ? "col-match" : "col-mismatch";
}

/** Parse a score input, falling back to the server default when unparseable. */
function parseScore(raw: string, fallback: number): number {
  const parsed = Number.parseFloat(raw);
  return Number.isNaN(parsed) ? fallback : parsed;
}

/** One character per column, coloured by column kind. */
function renderColumns(
  sequence: string,
  alignedA: string,
  alignedB: string,
  limit: number,
): ReactNode[] {
  const cells: ReactNode[] = [];
  for (let index = 0; index < limit; index += 1) {
    const a = alignedA[index] ?? GAP;
    const b = alignedB[index] ?? GAP;
    cells.push(
      <span key={index} className={columnClass(a, b)}>
        {sequence[index] ?? GAP}
      </span>,
    );
  }
  return cells;
}

/** Score/metrics summary plus the colour-coded alignment rows. */
function AlignmentResultPanel({
  result,
  database,
}: {
  result: AlignmentResponse;
  database: string;
}) {
  const counts = countColumns(result.aligned_a, result.aligned_b);
  const limit = Math.min(counts.columns, MAX_RENDERED_COLUMNS);
  // Rebuilt from the response, not from the form state, so a download always
  // reproduces the alignment on screen. `mode` is `string` in the schema
  // mirror; the API constrains it to "global" | "local" server-side.
  const exportParams: AlignParams = {
    accessionA: result.accession_a,
    accessionB: result.accession_b,
    database,
    mode: result.mode as AlignmentMode,
    match_score: result.match_score,
    mismatch_score: result.mismatch_score,
    open_gap_score: result.open_gap_score,
    extend_gap_score: result.extend_gap_score,
  };

  return (
    <>
      <dl className="kv" data-testid="align-result">
        <div>
          <dt>Accessions</dt>
          <dd>
            {result.accession_a} · {result.accession_b}
          </dd>
        </div>
        <div>
          <dt>Mode</dt>
          <dd data-testid="align-mode-value">{result.mode}</dd>
        </div>
        <div>
          <dt>Score</dt>
          <dd data-testid="align-score">{result.score}</dd>
        </div>
        <div>
          <dt>Columns</dt>
          <dd data-testid="align-columns">{counts.columns}</dd>
        </div>
        <div>
          <dt>Matches / mismatches / gaps</dt>
          <dd data-testid="align-counts">
            {counts.matches} / {counts.mismatches} / {counts.gaps}
          </dd>
        </div>
        <div>
          <dt>Aligned region A</dt>
          <dd>
            {result.start_a}–{result.end_a}
          </dd>
        </div>
        <div>
          <dt>Aligned region B</dt>
          <dd>
            {result.start_b}–{result.end_b}
          </dd>
        </div>
        <div>
          <dt>Scoring</dt>
          <dd>
            match {result.match_score}, mismatch {result.mismatch_score}, open
            gap {result.open_gap_score}, extend gap {result.extend_gap_score}
          </dd>
        </div>
      </dl>

      <h3>Alignment</h3>
      <p className="meta" data-testid="align-legend">
        <span className="col-match legend">match</span>{" "}
        <span className="col-mismatch legend">mismatch</span>{" "}
        <span className="col-gap legend">gap</span> · {result.accession_a} on
        top, {result.accession_b} below
      </p>
      <div className="alignment" data-testid="alignment-rows">
        <div className="alignment-row">
          {renderColumns(
            result.aligned_a,
            result.aligned_a,
            result.aligned_b,
            limit,
          )}
        </div>
        <div className="alignment-row">
          {renderColumns(
            result.aligned_b,
            result.aligned_a,
            result.aligned_b,
            limit,
          )}
        </div>
      </div>
      {counts.columns > limit ? (
        <p className="meta" data-testid="align-truncated">
          Showing the first {limit} of {counts.columns} columns.
        </p>
      ) : null}
      <p className="export-links">
        <a
          data-testid="align-export-json"
          href={alignmentJsonExportUrl(exportParams)}
          download
        >
          Download JSON
        </a>
        <a
          data-testid="align-export-text"
          href={alignmentTextExportUrl(exportParams)}
          download
        >
          Download text
        </a>
      </p>
    </>
  );
}

/**
 * Two accession inputs, a database selector, the alignment mode and the four
 * scoring parameters, calling the existing `alignSequences()` wrapper
 * (`GET /api/align`). The returned gapped strings are rendered column by
 * column with matches, mismatches, and gaps visually distinguished.
 */
export function AlignmentView({
  initialDatabase = "ncbi",
}: AlignmentViewProps) {
  const [database, setDatabase] = useState(initialDatabase);
  const [accessionA, setAccessionA] = useState("");
  const [accessionB, setAccessionB] = useState("");
  const [mode, setMode] = useState<AlignmentMode>("global");
  const [matchScore, setMatchScore] = useState("1");
  const [mismatchScore, setMismatchScore] = useState("-1");
  const [openGapScore, setOpenGapScore] = useState("-2");
  const [extendGapScore, setExtendGapScore] = useState("-0.5");
  const [result, setResult] = useState<AlignmentResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedA = accessionA.trim();
    if (trimmedA === "") {
      setError("Enter the first accession.");
      return;
    }
    setLoading(true);
    setError(null);
    const trimmedB = accessionB.trim();
    try {
      setResult(
        await alignSequences({
          accessionA: trimmedA,
          // Omitted rather than sent empty: the API's default is "" and it
          // treats a falsy accession B as "align A against itself".
          accessionB: trimmedB === "" ? undefined : trimmedB,
          database,
          mode,
          match_score: parseScore(matchScore, 1.0),
          mismatch_score: parseScore(mismatchScore, -1.0),
          open_gap_score: parseScore(openGapScore, -2.0),
          extend_gap_score: parseScore(extendGapScore, -0.5),
        }),
      );
    } catch (err: unknown) {
      setResult(null);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="align-heading">
      <h2 id="align-heading">Align two sequences</h2>
      <form
        className="align-form"
        onSubmit={(event) => void handleSubmit(event)}
      >
        <DatabaseSelector
          value={database}
          onChange={setDatabase}
          id="alignment-database-select"
        />
        <div className="field">
          <label htmlFor="align-accession-a">Accession A</label>
          <input
            id="align-accession-a"
            value={accessionA}
            onChange={(event) => setAccessionA(event.target.value)}
            placeholder="e.g. NM_000001.1"
          />
        </div>
        <div className="field">
          <label htmlFor="align-accession-b">
            Accession B (leave empty to align A with itself)
          </label>
          <input
            id="align-accession-b"
            value={accessionB}
            onChange={(event) => setAccessionB(event.target.value)}
            placeholder="e.g. NM_000001.1"
          />
        </div>
        <div className="field">
          <label htmlFor="align-mode">Mode</label>
          <select
            id="align-mode"
            value={mode}
            onChange={(event) => setMode(event.target.value as AlignmentMode)}
          >
            <option value="global">global</option>
            <option value="local">local</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="align-match-score">Match score</label>
          <input
            id="align-match-score"
            type="number"
            step="0.5"
            value={matchScore}
            onChange={(event) => setMatchScore(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="align-mismatch-score">Mismatch score</label>
          <input
            id="align-mismatch-score"
            type="number"
            step="0.5"
            value={mismatchScore}
            onChange={(event) => setMismatchScore(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="align-open-gap-score">Open gap score</label>
          <input
            id="align-open-gap-score"
            type="number"
            step="0.5"
            value={openGapScore}
            onChange={(event) => setOpenGapScore(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="align-extend-gap-score">Extend gap score</label>
          <input
            id="align-extend-gap-score"
            type="number"
            step="0.5"
            value={extendGapScore}
            onChange={(event) => setExtendGapScore(event.target.value)}
          />
        </div>
        <button type="submit" disabled={loading}>
          {loading ? "Aligning…" : "Align"}
        </button>
      </form>

      {error ? (
        <p className="error" data-testid="align-error">
          {error}
        </p>
      ) : null}

      {result ? <AlignmentResultPanel result={result} database={database} /> : null}
    </section>
  );
}


