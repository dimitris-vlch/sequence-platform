import { useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "./api/client";

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

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
          setError(err instanceof Error ? err.message : String(err));
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
        ) : error ? (
          <p className="error" data-testid="backend-status">
            Cannot reach the backend ({error}). Start it with:
            <code> uvicorn sequence_platform.main:app --reload</code> in{" "}
            <code>backend/</code>, then refresh this page.
          </p>
        ) : (
          <p data-testid="backend-status">Checking backend…</p>
        )}
      </section>

      <section aria-labelledby="next-steps-heading">
        <h2 id="next-steps-heading">Next</h2>
        <p>
          Stage 1 skeleton. Sequence search and analysis features arrive in
          the stages that follow.
        </p>
      </section>
    </main>
  );
}
