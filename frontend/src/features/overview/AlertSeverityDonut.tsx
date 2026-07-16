import type { SeverityCountDto } from "../../contracts";
import { humanize } from "../../lib/format";

const SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

export function AlertSeverityDonut({ label, rows, total }: {
  label: string;
  rows: readonly SeverityCountDto[];
  total: number;
}) {
  const counts = SEVERITY_ORDER.map((severity) => rows.find((row) => row.severity === severity)?.count ?? 0);
  const percentages = counts.map((count) => total > 0 ? Math.min((count / total) * 100, 100) : 0);
  const segments = SEVERITY_ORDER.map((severity, index) => {
    const count = counts[index] ?? 0;
    const percentage = percentages[index] ?? 0;
    const offset = percentages.slice(0, index).reduce((sum, value) => sum + value, 0);
    return { severity, count, percentage, offset };
  });

  return <figure aria-label={label} className="severity-donut">
    <div className="severity-donut-visual">
      <svg aria-hidden="true" viewBox="0 0 120 120">
        <circle className="severity-donut-track" cx="60" cy="60" pathLength="100" r="46" />
        {segments.map(({ severity, percentage, offset: segmentOffset }) => percentage > 0 ? <circle
          className={`severity-donut-segment tone-${severity.toLowerCase()}`}
          cx="60"
          cy="60"
          key={severity}
          pathLength="100"
          r="46"
          strokeDasharray={`${percentage} ${100 - percentage}`}
          strokeDashoffset={-segmentOffset}
        /> : null)}
      </svg>
      <div className="severity-donut-total"><strong>{total}</strong><span>{label}</span></div>
    </div>
    <figcaption>
      <ul className="severity-donut-legend">
        {segments.map(({ severity, count, percentage }) => <li className={`tone-${severity.toLowerCase()}`} key={severity}>
          <span><i aria-hidden="true" />{humanize(severity)}</span>
          <strong>{count}</strong>
          <small>{percentage.toLocaleString(undefined, { maximumFractionDigits: 1 })}%</small>
        </li>)}
      </ul>
    </figcaption>
  </figure>;
}
