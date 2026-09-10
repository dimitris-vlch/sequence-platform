import { useState, type FormEvent } from "react";

import {
  compareSequences,
  errorMessage,
  type ComparisonResponse,
} from "../api/client";
import { DatabaseSelector } from "./DatabaseSelector";

export interface ComparisonViewProps {
  /** Database selected when the view first renders. */
  initialDatabase?: string;
}

/** Render a nullable metric without inventing a value. */
function metric(value: number | null): string {
  return value === null ? "—" : String(value);
}

/**
 * Two accession inputs, a database selector, and the Stage 5 comparison
 * metrics returned by `GET /api/compare`. An empty second accession compares
 * the first record against itself (the backend's documented behaviour).
 */
export function ComparisonView({
  initialDatabase = "ncbi",
}: ComparisonViewProps) {
  const [database, setDatabase] = useState(initialDatabase);
  const [accessionA, setAccessionA] = useState("");
  const [accessionB, setAccessionB] = useState("");
  const [k, setK] = useState(4);
  const [result, setResult] = useState<ComparisonResponse | null>(null);
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
        await compareSequences({
          accessionA: trimmedA,
          // Omitted rather than sent empty: the API's default is "" and it
          // treats a falsy accession B as "compare A with itself".
          accessionB: trimmedB === "" ? undefined : trimmedB,
          database,
          k,
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
    <section aria-labelledby="compare-heading">
      <h2 id="compare-heading">Compare two sequences</h2>
      <form
        className="compare-form"
        onSubmit={(event) => void handleSubmit(event)}
      >
        <DatabaseSelector
          value={database}
          onChange={setDatabase}
          id="comparison-database-select"
        />
        <div className="field">
          <label htmlFor="compare-accession-a">Accession A</label>
          <input
            id="compare-accession-a"
            value={accessionA}
            onChange={(event) => setAccessionA(event.target.value)}
            placeholder="e.g. NM_000001.1"
          />
        </div>
        <div className="field">
          <label htmlFor="compare-accession-b">
            Accession B (leave empty to compare A with itself)
          </label>
          <input
            id="compare-accession-b"
            value={accessionB}
            onChange={(event) => setAccessionB(event.target.value)}
            placeholder="e.g. NM_000001.1"
          />
        </div>
        <div className="field">
          <label htmlFor="compare-k">k-mer size</label>
          <input
            id="compare-k"
            type="number"
            min={1}
            max={12}
            value={k}
            onChange={(event) => {
              const parsed = Number.parseInt(event.target.value, 10);
              setK(Number.isNaN(parsed) ? 4 : parsed);
            }}
          />
        </div>
        <button type="submit" disabled={loading}>
          {loading ? "Comparing…" : "Compare"}
        </button>
      </form>

      {error ? (
        <p className="error" data-testid="compare-error">
          {error}
        </p>
      ) : null}

      {result ? (
        <dl className="kv" data-testid="compare-result">
          <div>
            <dt>Accessions</dt>
            <dd>
              {result.accession_a} · {result.accession_b}
            </dd>
          </div>
          <div>
            <dt>Lengths</dt>
            <dd data-testid="compare-lengths">
              {result.length_a} · {result.length_b}
            </dd>
          </div>
          <div>
            <dt>Hamming distance</dt>
            <dd data-testid="compare-hamming">
              {metric(result.hamming_distance)}
            </dd>
          </div>
          <div>
            <dt>Percent identity</dt>
            <dd data-testid="compare-identity">
              {metric(result.percent_identity)}
            </dd>
          </div>
          <div>
            <dt>Levenshtein distance</dt>
            <dd>{result.levenshtein_distance}</dd>
          </div>
          <div>
            <dt>Normalised edit similarity</dt>
            <dd>{result.normalized_edit_similarity}</dd>
          </div>
          <div>
            <dt>Jaccard k-mer similarity (k={result.k})</dt>
            <dd>{result.jaccard_kmer_similarity}</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}
