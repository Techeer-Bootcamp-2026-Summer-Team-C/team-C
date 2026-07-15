import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { DataTable, DefinitionGrid, EmptyState, ErrorState, PageHeader, Panel, Skeleton, StatusPill } from "../components/ui";
import type { AttackTimelineDto, IncidentDetailDto } from "../contracts";
import { formatDateTime } from "../lib/format";
import { useI18n } from "../i18n/LocaleContext";

export function IncidentDetailPage() {
  const { t } = useI18n();
  const incidentId = Number(useParams().incidentId);
  const valid = Number.isInteger(incidentId) && incidentId > 0;
  const result = useQuery({ queryKey: ["incident", incidentId], queryFn: ({ signal }) => api.incident(incidentId, signal), enabled: valid });
  const timeline = useQuery({ queryKey: ["incident-timeline", incidentId], queryFn: ({ signal }) => api.incidentTimeline(incidentId, signal), enabled: valid });
  if (!valid) return <ErrorState error={new Error("The Incident ID is invalid.")} />;
  return <div className="page-stack">
    <Link className="back-link" to="/incidents"><ArrowLeft aria-hidden="true" size={15} />{t("incident.queue")}</Link>
    {result.isPending ? <Skeleton rows={10} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <IncidentDetail incident={result.data.data} /> : null}
    {result.data ? <Panel title={t("incident.attackTimeline")} subtitle={t("incident.attackTimelineSubtitle")} meta={<StatusPill value="READ ONLY" />}>
      {timeline.isPending ? <Skeleton rows={5} /> : null}
      {timeline.error ? <ErrorState error={timeline.error} onRetry={() => void timeline.refetch()} /> : null}
      {timeline.data ? <AttackTimeline timeline={timeline.data.data} /> : null}
    </Panel> : null}
  </div>;
}

function IncidentDetail({ incident }: { incident: IncidentDetailDto }) {
  const { t } = useI18n();
  return <>
    <PageHeader eyebrow={`INCIDENT ${incident.incidentId}`} title={incident.title} description={incident.description ?? t("incident.noDescription")} actions={<><StatusPill value={incident.severity} /><StatusPill value={incident.status} /></>} />
    <section className="detail-grid">
      <Panel title={t("incident.context")} subtitle={t("incident.contextSubtitle")}><DefinitionGrid items={[
        { label: t("incident.correlationKey"), value: <code>{incident.correlationKey}</code> },
        { label: "Endpoint", value: <Link to={`/endpoints/${incident.endpointId}`}>Endpoint {incident.endpointId}</Link> },
        { label: t("incident.alertCount"), value: incident.alertCount },
        { label: t("incident.windowStart"), value: formatDateTime(incident.windowStartAt) },
        { label: t("incident.windowEnd"), value: formatDateTime(incident.windowEndAt) },
        { label: t("incident.firstDetected"), value: formatDateTime(incident.firstDetectedAt) },
        { label: t("incident.lastDetected"), value: formatDateTime(incident.lastDetectedAt) },
        { label: t("incident.closed"), value: formatDateTime(incident.closedAt) },
      ]} /></Panel>
      <Panel title={t("incident.lifecycle")} subtitle={t("incident.noManualControls")}><div className="read-only-note"><StatusPill value={incident.status} /><span>{t("incident.backendLifecycle")}</span></div></Panel>
      <Panel className="wide" title={t("incident.connectedAlerts")} subtitle={t("incident.connectedSubtitle")}>{incident.alerts.length ? <DataTable label={t("incident.connectedAlerts")}><thead><tr><th scope="col">Alert</th><th scope="col">{t("filter.severity")}</th><th scope="col">{t("filter.status")}</th><th scope="col">{t("alerts.detected")}</th></tr></thead><tbody>{incident.alerts.map((alert) => <tr key={alert.alertId}><td><Link className="table-primary" to={`/alerts/${alert.alertId}`}><strong>{alert.title}</strong><code>{alert.ruleCode} · v{alert.ruleVersion}</code></Link></td><td><StatusPill value={alert.severity} /></td><td><StatusPill value={alert.status} /></td><td>{formatDateTime(alert.detectedAt)}</td></tr>)}</tbody></DataTable> : <EmptyState title={t("incident.noConnectedAlerts")} message={t("incident.noConnectedAlertsDescription")} />}</Panel>
    </section>
  </>;
}

function AttackTimeline({ timeline }: { timeline: AttackTimelineDto }) {
  const { t } = useI18n();
  if (!timeline.items.length) return <EmptyState title={t("incident.noTimelineEvidence")} message={t("incident.noTimelineDescription")} />;
  return <ol className="attack-timeline">{timeline.items.map((item, index) => <li key={`${item.itemType}-${item.occurredAt}-${index}`}>
    <span className={`timeline-marker tone-${item.itemType.toLowerCase()}`} />
    <div>
      <div className="timeline-heading"><StatusPill value={item.itemType} />{item.severity ? <StatusPill value={item.severity} /> : null}<time>{formatDateTime(item.occurredAt)}</time></div>
      <strong>{item.alertId ? <Link to={`/alerts/${item.alertId}`}>{item.title}</Link> : item.eventId ? <Link to={`/events/${item.eventId}?endpointId=${item.endpointId}&occurredAt=${encodeURIComponent(item.occurredAt)}`}>{item.title}</Link> : item.title}</strong>
      <p>{item.summary}</p>
    </div>
  </li>)}</ol>;
}
