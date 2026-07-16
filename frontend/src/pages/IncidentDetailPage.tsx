import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { IncidentInvestigation } from "../components/IncidentInvestigation";
import { ProcessTree } from "../components/ProcessTree";
import { Badge } from "../components/primitives";
import { DataTable, DefinitionGrid, EmptyState, ErrorState, PageHeader, Panel, PartialFailureWarning, Skeleton, StatusPill } from "../components/ui";
import type { AttackTimelineDto, IncidentDetailDto, IncidentDto, IncidentInvestigationDto } from "../contracts";
import {
  incidentDetailUrl,
  incidentQueueQuery,
  selectedProcessPid,
  selectionForTimelineItem,
  selectionMatchesTimelineItem,
  type InvestigationSelection,
} from "../features/incidentInvestigation";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime } from "../lib/format";

export function IncidentDetailPage() {
  const { t } = useI18n();
  const incidentId = Number(useParams().incidentId);
  const [params] = useSearchParams();
  const [selectionState, setSelectionState] = useState<{ incidentId: number; value: InvestigationSelection } | null>(null);
  const selection = selectionState?.incidentId === incidentId ? selectionState.value : null;
  const setSelection = (value: InvestigationSelection) => setSelectionState({ incidentId, value });
  const valid = Number.isInteger(incidentId) && incidentId > 0;
  const result = useQuery({ queryKey: ["incident", incidentId], queryFn: ({ signal }) => api.incident(incidentId, signal), enabled: valid });
  const timeline = useQuery({ queryKey: ["incident-timeline", incidentId], queryFn: ({ signal }) => api.incidentTimeline(incidentId, signal), enabled: valid });
  const investigation = useQuery({ queryKey: ["incident-investigation", incidentId], queryFn: ({ signal }) => api.incidentInvestigation(incidentId, signal), enabled: valid });
  const queueQuery = incidentQueueQuery(params);
  const queue = useQuery({ queryKey: ["incident-workbench-queue", queueQuery], queryFn: ({ signal }) => api.incidents(queueQuery, signal), enabled: valid });
  const investigationData = investigation.data?.data ?? null;
  const processPid = selectedProcessPid(selection, investigationData);
  const processTree = useQuery({
    queryKey: ["incident-process-tree", result.data?.data.endpointId, investigationData?.timeRange.from, investigationData?.timeRange.to, processPid],
    queryFn: ({ signal }) => api.processTree(result.data!.data.endpointId, {
      timePreset: "CUSTOM",
      from: investigationData!.timeRange.from,
      to: investigationData!.timeRange.to,
      selectedPid: processPid!,
    }, signal),
    enabled: Boolean(result.data && investigationData && processPid !== null),
  });
  if (!valid) return <ErrorState error={new Error("The Incident ID is invalid.")} />;
  return <div className="page-stack">
    <Link className="back-link" to={`/incidents${params.size ? `?${params}` : ""}`}><ArrowLeft aria-hidden="true" size={15} />{t("incident.queue")}</Link>
    {result.isPending ? <Skeleton rows={10} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <>
      <section aria-label={t("incident.workbench")} className="incident-workbench">
        <IncidentQueue currentIncidentId={incidentId} incidents={queue.data?.data.items ?? []} loading={queue.isPending} params={params} />
        <main className="incident-detail"><IncidentDetail incident={result.data.data} /></main>
      </section>
      <section aria-label={t("incident.investigation")} className="incident-evidence-workspace">
        {investigation.isPending ? <Skeleton rows={10} /> : null}
        {investigation.error ? <Panel title={t("incident.investigation")} subtitle={t("incident.graphFallbackDescription")}>
          <PartialFailureWarning message={t("incident.graphRequestFailed")} />
          <ErrorState error={investigation.error} onRetry={() => void investigation.refetch()} />
        </Panel> : null}
        {investigationData ? <IncidentInvestigation investigation={investigationData} onSelect={setSelection} selection={selection} /> : null}
        <Panel title={t("incident.attackTimeline")} subtitle={t("incident.attackTimelineSubtitle")} meta={<StatusPill value="READ ONLY" />}>
          {timeline.isPending ? <Skeleton rows={5} /> : null}
          {timeline.error ? <ErrorState error={timeline.error} onRetry={() => void timeline.refetch()} /> : null}
          {timeline.data ? <AttackTimeline investigation={investigationData} onSelect={setSelection} selection={selection} timeline={timeline.data.data} /> : null}
        </Panel>
        <Panel title={t("incident.processTree")} subtitle={t("incident.processTreeSubtitle")} meta={<StatusPill value="READ ONLY" />}>
          {processPid === null ? <EmptyState title={t("incident.selectProcess")} message={t("incident.selectProcessDescription")} /> : null}
          {processTree.isPending && processPid !== null ? <Skeleton rows={5} /> : null}
          {processTree.error ? <ErrorState error={processTree.error} onRetry={() => void processTree.refetch()} /> : null}
          {processTree.data ? <ProcessTree nodes={processTree.data.data.nodes} /> : null}
        </Panel>
      </section>
    </> : null}
  </div>;
}

function IncidentQueue({ currentIncidentId, incidents, loading, params }: { currentIncidentId: number; incidents: IncidentDto[]; loading: boolean; params: URLSearchParams }) {
  const { t } = useI18n();
  return <Panel className="incident-queue-panel" title={t("incident.activeQueue")} subtitle={t("incident.activeQueueDescription")} meta={<Badge tone="info">{incidents.length}</Badge>}>
    {loading ? <Skeleton rows={7} /> : incidents.length ? <nav aria-label={t("incident.activeQueue")} className="incident-queue">
      {incidents.map((incident) => <Link aria-current={incident.incidentId === currentIncidentId ? "page" : undefined} className={incident.incidentId === currentIncidentId ? "incident-queue-row selected" : "incident-queue-row"} key={incident.incidentId} to={incidentDetailUrl(incident.incidentId, params)}>
        <span><StatusPill value={incident.severity} /><StatusPill value={incident.status} /></span>
        <strong>{incident.title}</strong>
        <code>{incident.correlationKey}</code>
        <small>{t("incident.queueMeta", { alerts: incident.alertCount, time: formatDateTime(incident.lastDetectedAt) })}</small>
      </Link>)}
    </nav> : <EmptyState title={t("incident.noActiveQueue")} message={t("incident.noActiveQueueDescription")} />}
  </Panel>;
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

export function AttackTimeline({ timeline, investigation, selection, onSelect }: { timeline: AttackTimelineDto; investigation: IncidentInvestigationDto | null; selection: InvestigationSelection | null; onSelect: (selection: InvestigationSelection) => void }) {
  const { t } = useI18n();
  if (!timeline.items.length) return <EmptyState title={t("incident.noTimelineEvidence")} message={t("incident.noTimelineDescription")} />;
  return <ol className="attack-timeline">{timeline.items.map((item, index) => {
    const nextSelection = investigation ? selectionForTimelineItem(investigation, item) : null;
    const selected = investigation ? selectionMatchesTimelineItem(selection, investigation, item) : false;
    return <li aria-current={selected ? "true" : undefined} className={selected ? "selected" : undefined} key={`${item.itemType}-${item.occurredAt}-${index}`}>
      <span className={`timeline-marker tone-${item.itemType.toLowerCase()}`} />
      <div>
        <div className="timeline-heading"><StatusPill value={item.itemType} />{item.severity ? <StatusPill value={item.severity} /> : null}<time>{formatDateTime(item.occurredAt)}</time>{nextSelection ? <button aria-pressed={selected} className="timeline-select-control" onClick={() => onSelect(nextSelection)} type="button">{t("incident.selectEvidence")}</button> : null}</div>
        <strong>{item.alertId ? <Link to={`/alerts/${item.alertId}`}>{item.title}</Link> : item.eventId ? <Link to={`/events/${item.eventId}?endpointId=${item.endpointId}&occurredAt=${encodeURIComponent(item.occurredAt)}`}>{item.title}</Link> : item.title}</strong>
        <p>{item.summary}</p>
      </div>
    </li>;
  })}</ol>;
}
