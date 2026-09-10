import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts";

import {
  errorMessage,
  fetchQuality,
  fetchSequence,
  fetchStatistics,
  type QualityReportResponse,
  type SequenceRecordOut,
  type SequenceStatisticsResponse,
} from "../api/client";

export interface SequenceDetailProps {
  /** Provider to fetch from. */
  database: string;
  /** Accession to show. */
  accession: string;
}

interface DetailData {
  record: SequenceRecordOut;
  statistics: SequenceStatisticsResponse;
  quality: QualityReportResponse;
}

// ---------------------------------------------------------------------------
// Charts (Stage 8.5). Fixed pixel sizes rather than ResponsiveContainer: the
// panel is a fixed-width column, and a fixed size renders deterministically in
// jsdom, where there is no layout to measure.
// ---------------------------------------------------------------------------

/** Stable colour per composition category; unknown keys get the fallback. */
const BASE_COLORS: Record<string, string> = {
  A: "#5fd68a",
  C: "#6ea8fe",
  G: "#ffd166",
  T: "#ff7a7a",
  ambiguous: "#9aa3bd",
};
const FALLBACK_COLOR = "#8b7bd8";

const COMPOSITION_CHART_WIDTH = 220;
const COMPOSITION_CHART_HEIGHT = 180;
const QUALITY_CHART_WIDTH = 520;
const QUALITY_CHART_HEIGHT = 160;

/**
 * Base composition as a donut plus a legend that carries the exact numbers
 * (the pie shows the shape at a glance; the legend is what you read).
 */
function BaseCompositionChart({
  composition,
}: {
  composition: Record<string, number>;
}) {
  const entries = Object.entries(composition).map(([base, percent]) => ({
    base,
    percent,
    color: BASE_COLORS[base] ?? FALLBACK_COLOR,
  }));

  return (
    <div className="chart-panel" data-testid="composition-chart">
      <PieChart
        width={COMPOSITION_CHART_WIDTH}
        height={COMPOSITION_CHART_HEIGHT}
      >
        <Pie
          data={entries}
          dataKey="percent"
          nameKey="base"
          innerRadius={42}
          outerRadius={80}
          isAnimationActive={false}
        >
          {entries.map((entry) => (
            <Cell key={entry.base} fill={entry.color} />
          ))}
        </Pie>
      </PieChart>
      <ul className="composition">
        {entries.map((entry) => (
          <li key={entry.base}>
            <span
              className="legend-swatch"
              style={{ background: entry.color }}
              aria-hidden="true"
            />
            {entry.base}: {entry.percent}%
          </li>
        ))}
      </ul>
    </div>
  );
}

interface QualityMetricRow {
  label: string;
  measured: string;
  threshold: string;
  /** Measured value as a percentage of its threshold (100 = at the threshold). */
  percentOfThreshold: number;
}

/** The three QC checks as measured-vs-threshold rows. */
function qualityMetricRows(
  statistics: SequenceStatisticsResponse,
  quality: QualityReportResponse,
): QualityMetricRow[] {
  const ambiguousLimit = quality.max_ambiguous_fraction * 100;
  const raw = [
    {
      label: "Length",
      value: statistics.length,
      limit: quality.min_length,
      measured: `${statistics.length} bp`,
      threshold: `${quality.min_length} bp (min)`,
    },
    {
      label: "Ambiguous",
      value: statistics.ambiguous_percentage,
      limit: ambiguousLimit,
      measured: `${statistics.ambiguous_percentage}%`,
      threshold: `${ambiguousLimit}% (max)`,
    },
    {
      label: "Longest N-run",
      value: statistics.longest_n_run,
      limit: quality.max_n_run,
      measured: `${statistics.longest_n_run} bases`,
      threshold: `${quality.max_n_run} bases (max)`,
    },
  ];
  return raw.map((row) => ({
    label: row.label,
    measured: row.measured,
    threshold: row.threshold,
    // A zero limit makes the ratio meaningless; both raw numbers are still shown.
    percentOfThreshold: row.limit > 0 ? (row.value / row.limit) * 100 : 0,
  }));
}

/**
 * Quality metrics as horizontal bars of "% of threshold" — the dashed line at
 * 100 is the threshold itself — with the exact measured/threshold numbers
 * listed underneath. The pass/fail verdict stays the backend's
 * (`quality.passed` / `quality.issues`); the UI does not re-derive it.
 */
function QualityMetricsChart({
  statistics,
  quality,
}: {
  statistics: SequenceStatisticsResponse;
  quality: QualityReportResponse;
}) {
  const rows = qualityMetricRows(statistics, quality);
  const axisMax = Math.ceil(
    Math.max(100, ...rows.map((row) => row.percentOfThreshold)),
  );

  return (
    <div data-testid="quality-chart">
      <BarChart
        width={QUALITY_CHART_WIDTH}
        height={QUALITY_CHART_HEIGHT}
        data={rows}
        layout="vertical"
        margin={{ top: 8, right: 24, bottom: 8, left: 8 }}
      >
        <XAxis type="number" domain={[0, axisMax]} unit="%" />
        <YAxis type="category" dataKey="label" width={100} />
        <ReferenceLine
          x={100}
          stroke="#9aa3bd"
          strokeDasharray="4 4"
          label="threshold"
        />
        <Bar
          dataKey="percentOfThreshold"
          fill={quality.passed ? "#5fd68a" : "#ff7a7a"}
          isAnimationActive={false}
        />
      </BarChart>
      <ul className="quality-rows" data-testid="quality-rows">
        {rows.map((row) => (
          <li key={row.label}>
            {row.label}: {row.measured} / threshold {row.threshold} (
            {Math.round(row.percentOfThreshold)}% of threshold)
          </li>
        ))}
      </ul>
    </div>
  );
}


/**
 * One record with its statistics and quality report. The record, its
 * statistics, and its QC report are fetched together so a single loading and
 * error state covers the whole panel.
 */
export function SequenceDetail({ database, accession }: SequenceDetailProps) {
  const [data, setData] = useState<DetailData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    Promise.all([
      fetchSequence(database, accession),
      fetchStatistics(accession, database),
      fetchQuality(accession, database),
    ])
      .then(([record, statistics, quality]) => {
        if (!cancelled) {
          setData({ record, statistics, quality });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(errorMessage(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [database, accession]);

  if (loading) {
    return (
      <section aria-labelledby="detail-heading">
        <h2 id="detail-heading">{accession}</h2>
        <p data-testid="detail-loading">Loading {accession}…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section aria-labelledby="detail-heading">
        <h2 id="detail-heading">{accession}</h2>
        <p className="error" data-testid="detail-error">
          Cannot load {accession} ({error})
        </p>
      </section>
    );
  }

  if (!data) {
    return null;
  }

  const { record, statistics, quality } = data;

  return (
    <section aria-labelledby="detail-heading" data-testid="sequence-detail">
      <h2 id="detail-heading">{record.accession}</h2>
      <p className="meta">
        {record.description || record.title || "No description provided"}
      </p>
      <dl className="kv">
        <div>
          <dt>Type</dt>
          <dd>{record.seq_type}</dd>
        </div>
        <div>
          <dt>Length</dt>
          <dd>{record.length}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{record.source_database || "—"}</dd>
        </div>
      </dl>

      <h3>Sequence</h3>
      <pre className="sequence" data-testid="sequence-text">
        {record.sequence}
      </pre>

      <h3>Statistics</h3>
      <dl className="kv">
        <div>
          <dt>Length</dt>
          <dd data-testid="statistics-length">{statistics.length}</dd>
        </div>
        <div>
          <dt>GC content</dt>
          <dd data-testid="statistics-gc">
            {statistics.gc_content === null ? "—" : `${statistics.gc_content}%`}
          </dd>
        </div>
        <div>
          <dt>Ambiguous bases</dt>
          <dd>
            {statistics.ambiguous_count} ({statistics.ambiguous_percentage}%)
          </dd>
        </div>
        <div>
          <dt>N-runs</dt>
          <dd>
            {statistics.n_run_count} (longest {statistics.longest_n_run})
          </dd>
        </div>
      </dl>
      <h4>Base composition</h4>
      <BaseCompositionChart composition={statistics.base_composition} />

      <h3>Quality report</h3>
      <p
        className={quality.passed ? "ok" : "error"}
        data-testid="quality-status"
      >
        {quality.passed ? "Passed" : "Failed"}
      </p>
      {quality.issues.length > 0 ? (
        <ul data-testid="quality-issues">
          {quality.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      ) : null}
      <QualityMetricsChart statistics={statistics} quality={quality} />
    </section>
  );
}
