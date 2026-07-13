import type { IncidentTimeSeriesPointDto, SeverityCountDto, TimeSeriesPointDto } from "../contracts";
import { formatCompactDate, humanize } from "../lib/format";
import { EmptyState } from "./ui";

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "var(--color-red)",
  HIGH: "var(--color-amber)",
  MEDIUM: "var(--color-blue)",
  LOW: "var(--color-green)",
};

export function SeverityDonut({ rows, total }: { rows: SeverityCountDto[]; total: number }) {
  if (!rows.length || total === 0) return <EmptyState title="No alert severity data" message="No Alerts were detected in this time range." />;
  const stops = severityStops(rows, total);
  return <div className="donut-layout"><div className="donut" style={{ background: `conic-gradient(${stops.join(",")})` }} role="img" aria-label={`${total} alerts by severity`}><span><strong>{total}</strong><small>Alerts</small></span></div><ul className="chart-legend">{rows.map((row) => <li key={row.severity}><i style={{ background: SEVERITY_COLORS[row.severity] }} /><span>{humanize(row.severity)}</span><strong>{row.count}</strong></li>)}</ul></div>;
}

export function CountBars({ rows }: { rows: readonly { label: string; count: number; tone?: string }[] }) {
  if (!rows.length) return <EmptyState title="No distribution data" message="The Backend returned an empty distribution." />;
  const maximum = Math.max(...rows.map((row) => row.count), 1);
  return <div className="count-bars">{rows.map((row) => <div className="count-row" key={row.label}><div><span>{row.label}</span><strong>{row.count}</strong></div><span className={`count-track ${row.tone ?? ""}`}><i style={{ width: `${(row.count / maximum) * 100}%` }} /></span></div>)}</div>;
}

export function TimeSeriesChart({ rows, label }: { rows: TimeSeriesPointDto[]; label: string }) {
  if (!rows.length) return <EmptyState title={`No ${label.toLowerCase()} series`} message="No time buckets were returned for this range." />;
  const points = coordinates(rows.map((row) => row.count));
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ");
  return <div className="time-chart"><svg role="img" aria-label={`${label} time series`} viewBox="0 0 520 180"><path className="chart-grid" d="M20 30H500 M20 90H500 M20 150H500" /><path className="chart-line" d={path} />{points.map((point, index) => <circle cx={point.x} cy={point.y} key={rows[index]?.bucketStartAt} r="4"><title>{rows[index] ? `${formatCompactDate(rows[index].bucketStartAt)}: ${rows[index].count}` : ""}</title></circle>)}</svg><details><summary>View {label.toLowerCase()} data table</summary><table><thead><tr><th scope="col">Bucket</th><th scope="col">Count</th></tr></thead><tbody>{rows.map((row) => <tr key={row.bucketStartAt}><td>{formatCompactDate(row.bucketStartAt)}</td><td>{row.count}</td></tr>)}</tbody></table></details></div>;
}

export function IncidentSeriesChart({ rows }: { rows: IncidentTimeSeriesPointDto[] }) {
  if (!rows.length) return <EmptyState title="No incident series" message="No Incident time buckets were returned for this range." />;
  const open = coordinates(rows.map((row) => row.openCount));
  const closed = coordinates(rows.map((row) => row.closedCount));
  return <div className="time-chart"><svg role="img" aria-label="Incident open and closed time series" viewBox="0 0 520 180"><path className="chart-grid" d="M20 30H500 M20 90H500 M20 150H500" /><path className="chart-line alert" d={linePath(open)} /><path className="chart-line closed" d={linePath(closed)} /></svg><div className="inline-legend"><span><i className="open" />Open</span><span><i className="closed" />Closed</span></div><details><summary>View incident data table</summary><table><thead><tr><th scope="col">Bucket</th><th scope="col">Open</th><th scope="col">Closed</th></tr></thead><tbody>{rows.map((row) => <tr key={row.bucketStartAt}><td>{formatCompactDate(row.bucketStartAt)}</td><td>{row.openCount}</td><td>{row.closedCount}</td></tr>)}</tbody></table></details></div>;
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
