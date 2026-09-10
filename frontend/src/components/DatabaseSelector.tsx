import { useEffect, useState, type ChangeEvent } from "react";

import { errorMessage, fetchDatabases, type DatabaseInfo } from "../api/client";

export interface DatabaseSelectorProps {
  /** Currently selected provider name. */
  value: string;
  /** Called with the newly selected provider name. */
  onChange: (name: string) => void;
  /** Visible label for the control. */
  label?: string;
  /** DOM id for the select; distinct per instance so ids never collide. */
  id?: string;
}

/**
 * Dropdown of every archive the platform supports, loaded from
 * `GET /api/databases`. Providers with `available: false` are shown (the API
 * advertises them deliberately) but cannot be selected.
 */
export function DatabaseSelector({
  value,
  onChange,
  label = "Database",
  id = "database-select",
}: DatabaseSelectorProps) {
  const [databases, setDatabases] = useState<DatabaseInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDatabases()
      .then((result) => {
        if (!cancelled) {
          setDatabases(result.databases);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(errorMessage(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = databases.find((database) => database.name === value);

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        data-testid={id}
        value={value}
        onChange={(event: ChangeEvent<HTMLSelectElement>) =>
          onChange(event.target.value)
        }
      >
        {databases.length === 0 ? (
          <option value="">Loading…</option>
        ) : (
          databases.map((database) => (
            <option
              key={database.name}
              value={database.name}
              disabled={!database.available}
            >
              {database.available
                ? database.name
                : `${database.name} (unavailable)`}
            </option>
          ))
        )}
      </select>
      {selected && !selected.available ? (
        <p className="error" data-testid={`${id}-unavailable`}>
          No client is registered for {selected.name}; pick another database.
        </p>
      ) : null}
      {error ? (
        <p className="error" data-testid={`${id}-error`}>
          Cannot load databases ({error})
        </p>
      ) : null}
    </div>
  );
}
