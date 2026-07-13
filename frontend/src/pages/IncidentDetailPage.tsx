import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { DataTable, DefinitionGrid, EmptyState, ErrorState, PageHeader, Panel, Skeleton, StatusPill } from "../components/ui";
import type { AttackTimelineDto, IncidentDetailDto } from "../contracts";
import { formatDateTime } from "../lib/format";

export function IncidentDetailPage() {
  const incidentId = Number(useParams().incidentId);
  const valid = Number.isInteger(incidentId) && incidentId > 0;
  const result = useQuery({ queryKey: ["incident", incidentId], queryFn: ({ signal }) => api.incident(incidentId, signal), enabled: valid });
  const timeline = useQuery({ queryKey: ["incident-timeline", incidentId], queryFn: ({ signal }) => api.incidentTimeline(incidentId, signal), enabled: valid });
  if (!valid) return <ErrorState error={new Error("The Incident ID is invalid.")} />;
  return <div className="page-stack">
    <Link className="back-link" to="/incidents"><ArrowLeft aria-hidden="true" size={15} />Incident workbench</Link>
    {result.isPending ? <Skeleton rows={10} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <IncidentDetail incident={result.data.data} /> : null}
    {result.data ? <Panel title="Attack timeline" subtitle="Event → Alert → Incident evidence assembled by the Backend" meta={<StatusPill value="READ ONLY" />}>
      {timeline.isPending ? <Skeleton rows={5} /> : null}
      {timeline.error ? <ErrorState error={timeline.error} onRetry={() => void timeline.refetch()} /> : null}
      {timeline.data ? <AttackTimeline timeline={timeline.data.data} /> : null}
    </Panel> : null}
  </div>;
}

function IncidentDetail({ incident }: { incident: IncidentDetailDto }) {
  return <>
    <PageHeader eyebrow={`INCIDENT ${incident.incidentId}`} title={incident.title} description={incident.description ?? "No description was captured for this Incident."} actions={<><StatusPill value={incident.severity} /><StatusPill value={incident.status} /></>} />
    <section className="detail-grid">
      <Panel title="Correlation context" subtitle="Incident is a read-only Detection projection"><DefinitionGrid items={[
        { label: "Correlation key", value: <code>{incident.correlationKey}</code> },
        { label: "Endpoint", value: <Link to={`/endpoints/${incident.endpointId}`}>Endpoint {incident.endpointId}</Link> },
        { label: "Alert count", value: incident.alertCount },
        { label: "Window start", value: formatDateTime(incident.windowStartAt) },
        { label: "Window end", value: formatDateTime(incident.windowEndAt) },
        { label: "First detected", value: formatDateTime(incident.firstDetectedAt) },
        { label: "Last detected", value: formatDateTime(incident.lastDetectedAt) },
        { label: "Closed", value: formatDateTime(incident.closedAt) },
      ]} /></Panel>
      <Panel title="Lifecycle boundary" subtitle="No manual status or assignee controls"><div className="read-only-note"><StatusPill value={incident.status} /><span>Incident state is closed only by the Backend lifecycle task.</span></div></Panel>
      <Panel className="wide" title="Connected Alerts" subtitle="Alert snapshots attached to this Incident">{incident.alerts.length ? <DataTable label="Connected Alerts"><thead><tr><th scope="col">Alert</th><th scope="col">Severity</th><th scope="col">Status</th><th scope="col">Detected</th></tr></thead><tbody>{incident.alerts.map((alert) => <tr key={alert.alertId}><td><Link className="table-primary" to={`/alerts/${alert.alertId}`}><strong>{alert.title}</strong><code>{alert.ruleCode} · v{alert.ruleVersion}</code></Link></td><td><StatusPill value={alert.severity} /></td><td><StatusPill value={alert.status} /></td><td>{formatDateTime(alert.detectedAt)}</td></tr>)}</tbody></DataTable> : <EmptyState title="No connected Alerts" message="This Incident currently has no linked Alerts." />}</Panel>
    </section>
  </>;
}

function AttackTimeline({ timeline }: { timeline: AttackTimelineDto }) {
  if (!timeline.items.length) return <EmptyState title="No timeline evidence" message="No connected Event or Alert snapshots were found." />;
  return <ol className="attack-timeline">{timeline.items.map((item, index) => <li key={`${item.itemType}-${item.occurredAt}-${index}`}>
    <span className={`timeline-marker tone-${item.itemType.toLowerCase()}`} />
    <div>
      <div className="timeline-heading"><StatusPill value={item.itemType} />{item.severity ? <StatusPill value={item.severity} /> : null}<time>{formatDateTime(item.occurredAt)}</time></div>
      <strong>{item.alertId ? <Link to={`/alerts/${item.alertId}`}>{item.title}</Link> : item.eventId ? <Link to={`/events/${item.eventId}?endpointId=${item.endpointId}&occurredAt=${encodeURIComponent(item.occurredAt)}`}>{item.title}</Link> : item.title}</strong>
      <p>{item.summary}</p>
    </div>
  </li>)}</ol>;
}
