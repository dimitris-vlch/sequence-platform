import { useEffect, useState } from "react";

import { errorMessage, fetchHealth, type HealthResponse } from "./api/client";
import {
  AlignmentView,
  ComparisonView,
  DatabaseSelector,
  SequenceDetail,
  SequenceSearch,
} from "./components";

/** The three top-level panels; plain conditional rendering (no router). */
type View = "search" | "compare" | "align";

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [database, setDatabase] = useState("ncbi");
  const [selectedAccession, setSelectedAccession] = useState("");
  const [view, setView] = useState<View>("search");

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then((result) => {
        if (!cancelled) {
          setHealth(result);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setHealthError(errorMessage(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="app">
      <header>
        <h1>Sequence Platform</h1>
        <p className="tagline">
          Search, retrieve, and analyse public nucleotide sequences
        </p>
      </header>

      <section aria-labelledby="backend-status-heading">
        <h2 id="backend-status-heading">Backend status</h2>
        {health ? (
          <p className="ok" data-testid="backend-status">
            {health.service} v{health.version} is running
            <small> (supported databases: {health.databases.join(", ")})</small>
          </p>
        ) : healthError ? (
          <p className="error" data-testid="backend-status">
            Cannot reach the backend ({healthError}). Start it with:
            <code> uvicorn sequence_platform.main:app --reload</code> in{" "}
            <code>backend/</code>, then refresh this page.
          </p>
        ) : (
          <p data-testid="backend-status">Checking backend…</p>
        )}
      </section>

      <nav className="views" aria-label="Views">
        <button
          type="button"
          aria-pressed={view === "search"}
          onClick={() => setView("search")}
        >
          Search &amp; detail
        </button>
        <button
          type="button"
          aria-pressed={view === "compare"}
          onClick={() => setView("compare")}
        >
          Compare
        </button>
        <button
          type="button"
          aria-pressed={view === "align"}
          onClick={() => setView("align")}
        >
          Align
        </button>
      </nav>

      {view === "search" ? (
        <>
          <DatabaseSelector value={database} onChange={setDatabase} />
          <SequenceSearch database={database} onSelect={setSelectedAccession} />
          {selectedAccession ? (
            <SequenceDetail
              database={database}
              accession={selectedAccession}
              key={`${database}:${selectedAccession}`}
            />
          ) : (
            <p className="meta">Pick a search result to see its details.</p>
          )}
        </>
      ) : view === "compare" ? (
        <ComparisonView initialDatabase={database} />
      ) : (
        <AlignmentView initialDatabase={database} />
      )}
    </main>
  );
}

