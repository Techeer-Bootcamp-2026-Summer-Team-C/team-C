import type { EndpointSummaryDto } from "../../contracts";
import { useI18n } from "../../i18n/LocaleContext";
import { Panel } from "../../components/ui";

const RISK_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;
const SENSOR_STATES = ["HEALTHY", "DEGRADED", "UNAVAILABLE"] as const;
const RISK_LABEL_KEYS = {
  CRITICAL: "overview.riskCritical",
  HIGH: "overview.riskHigh",
  MEDIUM: "overview.riskMedium",
  LOW: "overview.riskLow",
} as const;
const SENSOR_LABEL_KEYS = {
  HEALTHY: "overview.sensorHealthy",
  DEGRADED: "overview.sensorDegraded",
  UNAVAILABLE: "overview.sensorUnavailable",
} as const;

export function FleetDistributionPanel({ summary }: { summary: EndpointSummaryDto }) {
  const { t } = useI18n();
  const riskDistribution = summary.risk.byLevel ?? [];
  const sensorHealth = summary.sensorHealth ?? [];
  const riskRows = RISK_LEVELS.map((level) => ({
    count: riskDistribution.find((row) => row.level === level)?.count ?? 0,
    level,
  }));
  const riskTotal = riskRows.reduce((total, row) => total + row.count, 0);
  const sensorRows = SENSOR_STATES.map((status) => ({
    count: sensorHealth.filter((row) => row.status === status).reduce((total, row) => total + row.count, 0),
    status,
  }));
  const sensorTotal = sensorRows.reduce((total, row) => total + row.count, 0);
  const sensorBreakdown = [...new Set(sensorHealth.map((row) => row.sensor))].sort().map((sensor) => {
    const rows = SENSOR_STATES.map((status) => ({
      count: sensorHealth.filter((row) => row.sensor === sensor && row.status === status).reduce((total, row) => total + row.count, 0),
      status,
    }));
    return { rows, sensor, total: rows.reduce((total, row) => total + row.count, 0) };
  });
  const riskLabel = (level: (typeof RISK_LEVELS)[number]) => t(RISK_LABEL_KEYS[level]);
  const sensorLabel = (status: (typeof SENSOR_STATES)[number]) => t(SENSOR_LABEL_KEYS[status]);
  const sensorSummary = (sensor: string, rows: typeof sensorRows, total: number) => t("overview.sensorStatusSummary", {
    degraded: rows.find((row) => row.status === "DEGRADED")?.count ?? 0,
    healthy: rows.find((row) => row.status === "HEALTHY")?.count ?? 0,
    sensor,
    total,
    unavailable: rows.find((row) => row.status === "UNAVAILABLE")?.count ?? 0,
  });

  return <Panel
    className="fleet-distribution-panel"
    meta={<span className="fleet-total">{t("overview.reportedEndpoints", { count: summary.totalCount })}</span>}
    subtitle={t("overview.fleetDistributionSubtitle")}
    title={t("overview.fleetDistribution")}
  >
    <div className="fleet-distribution">
      <section aria-labelledby="fleet-risk-heading" className="fleet-distribution-section">
        <header><h3 id="fleet-risk-heading">{t("overview.endpointRisk")}</h3><span>{t("overview.reportedRiskSnapshots", { count: riskTotal })}</span></header>
        {riskTotal ? <ul aria-label={t("overview.endpointRisk")} className="fleet-risk-list">
          {riskRows.map((row) => {
            const percentage = (row.count / riskTotal) * 100;
            return <li className={`tone-${row.level.toLowerCase()}`} key={row.level}>
              <span>{riskLabel(row.level)}</span>
              <div aria-label={`${riskLabel(row.level)}: ${row.count} / ${riskTotal}`} aria-valuemax={riskTotal} aria-valuemin={0} aria-valuenow={row.count} className="fleet-risk-track" role="progressbar"><i style={{ width: `${percentage}%` }} /></div>
              <strong>{row.count}</strong>
            </li>;
          })}
        </ul> : <p className="fleet-empty">{t("overview.noEndpointRiskSnapshot")}</p>}
      </section>

      <section aria-labelledby="fleet-sensor-heading" className="fleet-distribution-section">
        <header><h3 id="fleet-sensor-heading">{t("overview.sensorHealth")}</h3><span>{t("overview.reportedSensorChecks", { count: sensorTotal })}</span></header>
        {sensorTotal ? <>
          <div aria-label={sensorSummary(t("overview.allSensors"), sensorRows, sensorTotal)} className="sensor-health-stack" role="img">
            {sensorRows.filter((row) => row.count > 0).map((row) => <i className={`tone-${row.status.toLowerCase()}`} key={row.status} style={{ width: `${(row.count / sensorTotal) * 100}%` }} />)}
          </div>
          <ul aria-label={t("overview.sensorHealth")} className="sensor-health-legend">
            {sensorRows.map((row) => <li className={`tone-${row.status.toLowerCase()}`} key={row.status}><span>{sensorLabel(row.status)}</span><strong>{row.count}</strong></li>)}
          </ul>
          <div className="sensor-breakdown">
            <h4>{t("overview.sensorByType")}</h4>
            <ul>
              {sensorBreakdown.map((group) => <li key={group.sensor}>
                <div className="sensor-breakdown-heading">
                  <strong title={humanize(group.sensor)}>{humanize(group.sensor)}</strong>
                  <ul aria-label={sensorSummary(humanize(group.sensor), group.rows, group.total)} className="sensor-breakdown-statuses">
                    {group.rows.map((row) => <li className={`tone-${row.status.toLowerCase()}`} key={row.status}><span>{sensorLabel(row.status)}</span><strong>{row.count}</strong></li>)}
                  </ul>
                </div>
                <div aria-hidden="true" className="sensor-health-stack compact">
                  {group.rows.filter((row) => row.count > 0).map((row) => <i className={`tone-${row.status.toLowerCase()}`} key={row.status} style={{ width: `${(row.count / group.total) * 100}%` }} />)}
                </div>
              </li>)}
            </ul>
          </div>
        </> : <p className="fleet-empty">{t("overview.noSensorHealthSnapshots")}</p>}
      </section>
    </div>
  </Panel>;
}

function humanize(value: string): string {
  return value.toLowerCase().replaceAll("_", " ").replace(/(^|\s)\S/g, (character) => character.toUpperCase());
}
