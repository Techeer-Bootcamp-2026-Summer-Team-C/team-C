import { Link } from "react-router-dom";
import type { EndpointDto, IncidentDto } from "../../contracts";
import { useI18n } from "../../i18n/LocaleContext";
import { formatDateTime } from "../../lib/format";
import { DataTable, EmptyState, StatusPill } from "../../components/ui";

export function RiskEndpointTable({ endpoints }: { endpoints: EndpointDto[] }) {
  const { t } = useI18n();
  if (!endpoints.length) return <EmptyState title={t("overview.noEndpoints")} message={t("overview.noEndpointRiskSnapshot")} />;
  return <DataTable label={t("overview.highestRiskEndpoints")}><thead><tr>
    <th scope="col">{t("overview.endpoint")}</th>
    <th scope="col">{t("overview.riskScore")}</th>
    <th scope="col">{t("navigation.alerts")}</th>
    <th scope="col">{t("navigation.incidents")}</th>
  </tr></thead><tbody>{endpoints.map((endpoint) => <tr key={endpoint.endpointId}>
    <th scope="row"><Link to={`/endpoints/${endpoint.endpointId}`}>{endpoint.hostname}</Link><small>ID {endpoint.endpointId}</small></th>
    <td><div className={`queue-risk tone-${endpoint.risk.level.toLowerCase()}`}><span><strong>{endpoint.risk.score}</strong><StatusPill value={endpoint.risk.level} /></span><i aria-label={`${endpoint.risk.score} / 100`} aria-valuemax={100} aria-valuemin={0} aria-valuenow={endpoint.risk.score} role="progressbar"><b style={{ width: `${endpoint.risk.score}%` }} /></i></div></td>
    <td>{endpoint.risk.activeAlertCount}</td>
    <td>{endpoint.risk.openIncidentCount}</td>
  </tr>)}</tbody></DataTable>;
}

export function IncidentQueueTable({ incidents }: { incidents: IncidentDto[] }) {
  const { t } = useI18n();
  if (!incidents.length) return <EmptyState title={t("overview.noOpenIncidents")} message={t("overview.noOpenIncidentsDescription")} />;
  return <DataTable label={t("overview.incidentQueueWidget")}><thead><tr>
    <th scope="col">{t("overview.incident")}</th>
    <th scope="col">{t("overview.status")}</th>
    <th scope="col">{t("navigation.alerts")}</th>
    <th scope="col">{t("overview.lastDetected")}</th>
  </tr></thead><tbody>{incidents.map((incident) => <tr key={incident.incidentId}>
    <th scope="row"><Link to={`/incidents/${incident.incidentId}`}>{incident.title}</Link><small>ID {incident.incidentId}</small></th>
    <td><span className="queue-status"><StatusPill value={incident.severity} /><StatusPill value={incident.status} /></span></td>
    <td>{incident.alertCount}</td>
    <td><time dateTime={incident.lastDetectedAt}>{formatDateTime(incident.lastDetectedAt)}</time></td>
  </tr>)}</tbody></DataTable>;
}
