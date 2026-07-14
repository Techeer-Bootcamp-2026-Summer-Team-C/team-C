import type { IncidentTimeSeriesPointDto, SeverityCountDto, TimeSeriesPointDto } from "../contracts";
import type { WidgetDisplayMode } from "../features/dashboardLayout";
import { formatCompactDate, humanize } from "../lib/format";
import { EmptyState } from "./ui";

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "var(--color-red)",
  HIGH: "var(--color-amber)",
  MEDIUM: "var(--color-blue)",
  LOW: "var(--color-green)",
};

export function SeverityDonut({ rows, total, mode = "standard" }: { rows: SeverityCountDto[]; total: number; mode?: WidgetDisplayMode }) {
  if (!rows.length || total === 0) return <EmptyState title="No alert severity data" message="No Alerts were detected in this time range." />;
  const stops = severityStops(rows, total);
  return <div className={`donut-layout ${mode}`}><div className="donut" style={{ background: `conic-gradient(${stops.join(",")})` }} role="img" aria-label={`${total} alerts by severity`}><span><strong>{total}</strong><small>Alerts</small></span></div><ul className="chart-legend">{rows.map((row) => <li key={row.severity}><i style={{ background: SEVERITY_COLORS[row.severity] }} /><span>{humanize(row.severity)}</span><strong>{row.count}</strong></li>)}</ul></div>;
}

export function CountBars({ rows, mode = "standard" }: { rows: readonly { label: string; count: number; tone?: string }[]; mode?: WidgetDisplayMode }) {
  if (!rows.length) return <EmptyState title="No distribution data" message="The Backend returned an empty distribution." />;
  const maximum = Math.max(...rows.map((row) => row.count), 1);
  const visibleRows = mode === "compact" ? rows.slice(0, 3) : mode === "standard" ? rows.slice(0, 4) : rows;
  return <div className="count-bars"><DistributionRows maximum={maximum} rows={visibleRows} />{visibleRows.length < rows.length ? <details className="distribution-details"><summary>View {rows.length - visibleRows.length} more values</summary><div className="count-bars"><DistributionRows maximum={maximum} rows={rows} /></div></details> : null}</div>;
}

export function TimeSeriesChart({ rows, label, mode = "standard" }: { rows: TimeSeriesPointDto[]; label: string; mode?: WidgetDisplayMode }) {
  if (!rows.length) return <EmptyState title={`No ${label.toLowerCase()} series`} message="No time buckets were returned for this range." />;
  const chartRows = mode === "compact" ? sampleRows(rows, 8) : rows;
  const points = coordinates(chartRows.map((row) => row.count));
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ");
  const counts = rows.map((row) => row.count);
  return <div className={`time-chart ${mode}`}><svg role="img" aria-label={`${label} time series`} viewBox="0 0 520 180"><path className="chart-grid" d="M20 30H500 M20 90H500 M20 150H500" /><path className="chart-line" d={path} />{points.map((point, index) => <circle cx={point.x} cy={point.y} key={chartRows[index]?.bucketStartAt} r={mode === "compact" ? "3" : "4"}><title>{chartRows[index] ? `${formatCompactDate(chartRows[index].bucketStartAt)}: ${chartRows[index].count}` : ""}</title></circle>)}</svg>{mode === "expanded" ? <dl className="chart-stats"><div><dt>Minimum</dt><dd>{Math.min(...counts)}</dd></div><div><dt>Average</dt><dd>{Math.round(counts.reduce((sum, count) => sum + count, 0) / counts.length)}</dd></div><div><dt>Maximum</dt><dd>{Math.max(...counts)}</dd></div></dl> : null}<details><summary>View {label.toLowerCase()} data table</summary><table><thead><tr><th scope="col">Bucket</th><th scope="col">Count</th></tr></thead><tbody>{rows.map((row) => <tr key={row.bucketStartAt}><td>{formatCompactDate(row.bucketStartAt)}</td><td>{row.count}</td></tr>)}</tbody></table></details></div>;
}

export function IncidentSeriesChart({ rows, mode = "standard" }: { rows: IncidentTimeSeriesPointDto[]; mode?: WidgetDisplayMode }) {
  if (!rows.length) return <EmptyState title="No incident series" message="No Incident time buckets were returned for this range." />;
  const chartRows = mode === "compact" ? sampleRows(rows, 8) : rows;
  const open = coordinates(chartRows.map((row) => row.openCount));
  const closed = coordinates(chartRows.map((row) => row.closedCount));
  return <div className={`time-chart ${mode}`}><svg role="img" aria-label="Incident open and closed time series" viewBox="0 0 520 180"><path className="chart-grid" d="M20 30H500 M20 90H500 M20 150H500" /><path className="chart-line alert" d={linePath(open)} /><path className="chart-line closed" d={linePath(closed)} /></svg><div className="inline-legend"><span><i className="open" />Open</span><span><i className="closed" />Closed</span></div><details><summary>View incident data table</summary><table><thead><tr><th scope="col">Bucket</th><th scope="col">Open</th><th scope="col">Closed</th></tr></thead><tbody>{rows.map((row) => <tr key={row.bucketStartAt}><td>{formatCompactDate(row.bucketStartAt)}</td><td>{row.openCount}</td><td>{row.closedCount}</td></tr>)}</tbody></table></details></div>;
}

function DistributionRows({ rows, maximum }: { rows: readonly { label: string; count: number; tone?: string }[]; maximum: number }) {
  return <>{rows.map((row) => <div className="count-row" key={row.label}><div><span title={row.label}>{row.label}</span><strong>{row.count}</strong></div><span className={`count-track ${row.tone ?? ""}`}><i style={{ width: `${(row.count / maximum) * 100}%` }} /></span></div>)}</>;
}

function sampleRows<Row>(rows: Row[], maximum: number): Row[] {
  if (rows.length <= maximum) return rows;
  const stride = Math.ceil(rows.length / maximum);
  const sampled = rows.filter((_row, index) => index % stride === 0);
  const last = rows.at(-1);
  if (last && sampled.at(-1) !== last) sampled.push(last);
  return sampled;
}

function coordinates(values: number[]): { x: number; y: number }[] {
  const maximum = Math.max(...values, 1);
  return values.map((value, index) => ({
    x: values.length === 1 ? 260 : 20 + (index * 480) / Math.max(values.length - 1, 1),
    y: 150 - (value / maximum) * 120,
  }));
}

function severityStops(rows: SeverityCountDto[], total: number): string[] {
  let cursor = 0;
  const stops: string[] = [];
  for (const row of rows) {
    const start = cursor;
    cursor += (row.count / total) * 360;
    stops.push(`${SEVERITY_COLORS[row.severity]} ${start}deg ${cursor}deg`);
  }
  return stops;
}

function linePath(points: { x: number; y: number }[]): string {
  return points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ");
}
