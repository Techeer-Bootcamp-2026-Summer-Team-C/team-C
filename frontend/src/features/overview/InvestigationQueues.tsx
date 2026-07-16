import { Link } from "react-router-dom";
import { StatusPill, EmptyState } from "../../components/ui";
import type { EndpointDto, IncidentDto } from "../../contracts";
import { useI18n } from "../../i18n/LocaleContext";
import { formatDateTime, formatQueueDateTime, humanize } from "../../lib/format";

export function RiskEndpointRanking({ endpoints }: { endpoints: EndpointDto[] }) {
  const { t } = useI18n();
  if (!endpoints.length) return <EmptyState title={t("overview.noEndpoints")} message={t("overview.noEndpointRiskSnapshot")} />;
  return <ol aria-label={t("overview.highestRiskEndpoints")} className="investigation-list risk-endpoint-ranking">
    {endpoints.map((endpoint, index) => <li key={endpoint.endpointId}>
      <span aria-hidden="true" className="queue-rank">{String(index + 1).padStart(2, "0")}</span>
      <div className="queue-primary">
        <Link title={endpoint.hostname} to={`/endpoints/${endpoint.endpointId}`}>{endpoint.hostname}</Link>
        <small title={endpoint.agentId}>ID {endpoint.endpointId} · {endpoint.agentId}</small>
      </div>
      <div className="risk-ranking-metrics">
        <div className={`risk-ledger-score tone-${endpoint.risk.level.toLowerCase()}`}><span>{t("overview.riskScore")}</span><strong>{endpoint.risk.score}</strong><small>{humanize(endpoint.risk.level)}</small></div>
        <div><span>{t("navigation.alerts")}</span><strong>{endpoint.risk.activeAlertCount}</strong></div>
        <div><span>{t("navigation.incidents")}</span><strong>{endpoint.risk.openIncidentCount}</strong></div>
      </div>
    </li>)}
  </ol>;
}

export function IncidentQueueList({ incidents }: { incidents: IncidentDto[] }) {
  const { t } = useI18n();
  if (!incidents.length) return <EmptyState title={t("overview.noOpenIncidents")} message={t("overview.noOpenIncidentsDescription")} />;
  return <ol aria-label={t("overview.incidentQueueWidget")} className="investigation-list incident-queue-list">
    {incidents.map((incident) => <li key={incident.incidentId}>
      <div className="queue-primary">
        <Link title={incident.title} to={`/incidents/${incident.incidentId}`}>{incident.title}</Link>
        <small>ID {incident.incidentId}</small>
      </div>
      <div className="incident-queue-meta">
        <StatusPill value={incident.severity} />
        <span className="incident-state">{humanize(incident.status)}</span>
        <span className="incident-alert-count"><span className="sr-only">{t("navigation.alerts")}: </span>{incident.alertCount}</span>
        <time dateTime={incident.lastDetectedAt} title={formatDateTime(incident.lastDetectedAt)}>{formatQueueDateTime(incident.lastDetectedAt)}</time>
      </div>
    </li>)}
  </ol>;
}
