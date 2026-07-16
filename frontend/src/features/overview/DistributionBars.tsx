import type { SeverityCountDto } from "../../contracts";
import { humanize } from "../../lib/format";

const DISTRIBUTION_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

export function DistributionBars({ rows, total, label }: {
  rows: readonly { category: string; count: number }[];
  total: number;
  label: string;
}) {
  return <ul aria-label={label} className="distribution-bars">
    {DISTRIBUTION_ORDER.map((category) => {
      const count = rows.find((row) => row.category === category)?.count ?? 0;
      const percentage = total > 0 ? (count / total) * 100 : 0;
      const displayPercentage = percentage.toLocaleString(undefined, { maximumFractionDigits: 1 });
      return <li className={`tone-${category.toLowerCase()}`} key={category}>
        <div><span>{humanize(category)}</span><strong>{count}<small>{displayPercentage}%</small></strong></div>
        <div
          aria-label={`${humanize(category)}: ${count}, ${displayPercentage}%`}
          aria-valuemax={100}
          aria-valuemin={0}
          aria-valuenow={Math.min(percentage, 100)}
          className="distribution-track"
          role="progressbar"
        ><i style={{ width: `${Math.min(percentage, 100)}%` }} /></div>
      </li>;
    })}
  </ul>;
}

export function severityDistributionRows(rows: readonly SeverityCountDto[]): { category: string; count: number }[] {
  return rows.map((row) => ({ category: row.severity, count: row.count }));
}
