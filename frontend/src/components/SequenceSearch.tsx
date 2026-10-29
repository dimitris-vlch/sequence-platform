import { useState, type FormEvent } from "react";

import { errorMessage, searchSequences, type SearchResponse } from "../api/client";

export interface SequenceSearchProps {
  /** Provider to search in (from the app-level database selector). */
  database: string;
  /** Called with a hit's accession when the user opens it. */
  onSelect: (accession: string) => void;
}

/** Free-text search form plus its results list. */
export function SequenceSearch({ database, onSelect }: SequenceSearchProps) {
  const [query, setQuery] = useState("");
  const [maxResults, setMaxResults] = useState(20);
  const [result, setResult] = useState<{
    database: string;
    response: SearchResponse;
  } | null>(null);
  // Results belong to the database they were searched in. After the user
  // switches databases, showing them would make a click open the accession
  // in the *new* database (wrong record or a 404), so they are hidden.
  const response = result !== null && result.database === database ? result.response : null;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed === "") {
      setError("Enter a search term.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setResult({
        database,
        response: await searchSequences(database, trimmed, maxResults),
      });
    } catch (err: unknown) {
      setResult(null);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="search-heading">
      <h2 id="search-heading">Search sequences</h2>
      <form
        className="search-form"
        onSubmit={(event) => void handleSubmit(event)}
      >
        <div className="field">
          <label htmlFor="search-query">Query</label>
          <input
            id="search-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. Homo sapiens BRCA1 mRNA"
          />
        </div>
        <div className="field">
          <label htmlFor="search-max-results">Max results</label>
          <input
            id="search-max-results"
            type="number"
            min={1}
            max={100}
            value={maxResults}
            onChange={(event) => {
              const parsed = Number.parseInt(event.target.value, 10);
              // Clamp to the backend's 1..100 bound so an out-of-range value
              // never turns into a validation error.
              setMaxResults(
                Number.isNaN(parsed) ? 20 : Math.min(100, Math.max(1, parsed)),
              );
            }}
          />
        </div>
        <button type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error ? (
        <p className="error" data-testid="search-error">
          {error}
        </p>
      ) : null}

      {response ? (
        response.results.length === 0 ? (
          <p data-testid="search-empty">
            No results for &ldquo;{response.query}&rdquo; in {database}.
          </p>
        ) : (
          <table className="results">
            <thead>
              <tr>
                <th scope="col">Accession</th>
                <th scope="col">Title</th>
                <th scope="col">Length</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {response.results.map((hit) => (
                <tr key={`${hit.source_database}:${hit.accession}`}>
                  <td>
                    <button
                      type="button"
                      onClick={() => onSelect(hit.accession)}
                    >
                      {hit.accession}
                    </button>
                  </td>
                  <td>{hit.title || "—"}</td>
                  <td>{hit.length === null ? "—" : hit.length}</td>
                  <td>{hit.source_database || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      ) : null}
    </section>
  );
}
