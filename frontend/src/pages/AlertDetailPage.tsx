import { useMutation, useQuery, useQueryClient, type QueryClient, type UseMutationResult } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Save } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { readTimeFilter } from "../components/filters";
import { DefinitionGrid, EmptyState, ErrorState, Field, PageHeader, Panel, ResponseGuidance, Skeleton, SourceEvent, StatusPill } from "../components/ui";
import type { AlertDto, AlertListQuery, AlertStatus, SuccessEnvelope } from "../contracts";
import { alertDetailUrl, nextActionableAlert } from "../features/alertTriage";
import { formatDateTime } from "../lib/format";
import { allowedValue, positiveInteger } from "../lib/params";
import { canMutate } from "../query/policy";

export function AlertDetailPage() {
  const alertId = Number(useParams().alertId);
  const valid = Number.isInteger(alertId) && alertId > 0;
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const auth = useAuth();
  const queryClient = useQueryClient();
  const time = readTimeFilter(params);
  const queueQuery = triageQueueQuery(params);
  const result = useQuery({ queryKey: ["alert", alertId], queryFn: ({ signal }) => api.alert(alertId, signal), enabled: valid });
  const queueResult = useQuery({
    queryKey: ["alert-triage-queue", queueQuery],
    queryFn: ({ signal }) => api.alerts(queueQuery, signal),
    enabled: valid && time.valid,
  });
  const nextAlert = nextActionableAlert(queueResult.data?.data.items ?? [], alertId);
  const mutation = useMutation({
    mutationFn: (submission: TriageSubmission) => api.updateAlert(alertId, { status: submission.status }),
    onSuccess: async (_data, submission) => {
      await invalidateAlertData(queryClient, alertId);
      if (submission.nextAlertId) navigate(alertDetailUrl(submission.nextAlertId, params));
    },
  });
  if (!valid) return <ErrorState error={new Error("The Alert ID is invalid.")} />;
  const backUrl = `/alerts${params.size ? `?${params.toString()}` : ""}`;
  return <div className="page-stack">
    <Link className="back-link" to={backUrl}><ArrowLeft aria-hidden="true" size={15} />Alert queue</Link>
    {result.isPending ? <Skeleton rows={10} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <AlertDetail
      alert={result.data.data}
      canUpdate={auth.user ? canMutate(auth.user.role) : false}
      key={result.data.data.alertId}
      mutation={mutation}
      nextAlert={nextAlert}
      params={params}
      queue={queueResult.data?.data.items ?? []}
      queueError={queueResult.error}
      queuePending={queueResult.isPending}
    /> : null}
  </div>;
}

interface TriageSubmission {
  status: AlertStatus;
  nextAlertId?: number;
}

function triageQueueQuery(params: URLSearchParams): AlertListQuery {
  const time = readTimeFilter(params);
  const query: AlertListQuery = { ...time.query, page: 1, size: 500, sortOrder: allowedValue(params.get("sortOrder"), ["asc", "desc"] as const) ?? "desc" };
  const severity = allowedValue(params.get("severity"), ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const);
  const endpointId = positiveInteger(params.get("endpointId"));
  const ruleCode = (params.get("ruleCode") ?? "").trim();
  if (severity) query.severity = severity;
  if (endpointId) query.endpointId = endpointId;
  if (ruleCode) query.ruleCode = ruleCode;
  return query;
}

export async function invalidateAlertData(queryClient: Pick<QueryClient, "invalidateQueries">, alertId: number) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["alert", alertId] }),
    queryClient.invalidateQueries({ queryKey: ["alerts"] }),
    queryClient.invalidateQueries({ queryKey: ["endpoints"] }),
  ]);
}

function AlertDetail({ alert, canUpdate, mutation, nextAlert, params, queue, queueError, queuePending }: {
  alert: import("../contracts").AlertDetailDto;
  canUpdate: boolean;
  mutation: UseMutationResult<SuccessEnvelope<AlertDto>, Error, TriageSubmission>;
  nextAlert: AlertDto | null;
  params: URLSearchParams;
  queue: AlertDto[];
  queueError: unknown;
  queuePending: boolean;
}) {
  const [draftStatus, setDraftStatus] = useState<AlertStatus>(alert.status);
  const activeQueue = queue.filter((item) => item.status !== "RESOLVED" || item.alertId === alert.alertId);
  return <section className="triage-workspace">
    <Panel className="triage-queue-panel" title="Active alert queue" subtitle={`${queue.filter((item) => item.status !== "RESOLVED").length} Alerts require action`}>
      {queuePending ? <Skeleton rows={8} /> : null}
      {queueError ? <ErrorState error={queueError} /> : null}
      {!queuePending && !queueError ? <div className="triage-queue" aria-label="Active alert queue">
        {activeQueue.map((item) => <Link
          aria-current={item.alertId === alert.alertId ? "page" : undefined}
          className={item.alertId === alert.alertId ? "triage-row selected" : "triage-row"}
          key={item.alertId}
          to={alertDetailUrl(item.alertId, params)}
        >
          <span><StatusPill value={item.severity} /><small>Risk {item.riskScore}</small></span>
          <strong>{item.title}</strong>
          <code>{item.ruleCode} · {item.agentId}</code>
          <small>{formatDateTime(item.detectedAt)}</small>
        </Link>)}
        {!activeQueue.length ? <EmptyState title="Queue cleared" message="No unresolved Alerts match the current time, severity, endpoint, and rule filters." /> : null}
      </div> : null}
    </Panel>
    <div className="triage-detail page-stack">
      <PageHeader eyebrow={`${alert.ruleCode} · RULE V${alert.ruleVersion}`} title={alert.title} description={alert.summary} actions={<><StatusPill value={alert.severity} /><StatusPill value={alert.status} /></>} />
      {mutation.error ? <ErrorState error={mutation.error} /> : null}
      {mutation.isSuccess ? <div className="mutation-success"><CheckCircle2 aria-hidden="true" size={16} />Alert workflow state saved.</div> : null}
      <section className="detail-grid">
        <Panel title="Alert evidence" subtitle={`Detected ${formatDateTime(alert.detectedAt)}`}><DefinitionGrid items={[
          { label: "Alert ID", value: alert.alertId },
          { label: "Risk score", value: `${alert.riskScore} / 100` },
          { label: "Rule", value: `${alert.ruleName} · ${alert.ruleCode}` },
          { label: "Endpoint", value: <Link to={`/endpoints/${alert.endpointId}`}>Endpoint {alert.endpointId}</Link> },
          { label: "Agent ID", value: <code>{alert.agentId}</code> },
          { label: "Event ID", value: <code>{alert.eventId}</code> },
          { label: "MITRE tactic", value: `${alert.mitreTacticCode} · ${alert.mitreTacticName}` },
          { label: "MITRE technique", value: `${alert.mitreTechniqueCode} · ${alert.mitreTechniqueName}` },
          { label: "Updated", value: formatDateTime(alert.updatedAt) },
        ]} /></Panel>
        <Panel title="Workflow state" subtitle={canUpdate ? "Save this Alert or continue directly to the next unresolved item" : "VIEWER access is read-only"}>{canUpdate ? <div className="workflow-controls">
          <Field label="Alert status"><select disabled={mutation.isPending} onChange={(event) => setDraftStatus(event.target.value as AlertStatus)} value={draftStatus}><option>OPEN</option><option>IN_PROGRESS</option><option>RESOLVED</option></select></Field>
          <div className="workflow-actions">
            <button className="button ghost" disabled={mutation.isPending || draftStatus === alert.status} onClick={() => mutation.mutate({ status: draftStatus })} type="button"><Save aria-hidden="true" size={15} />Save status</button>
            <button className="button" disabled={mutation.isPending || !nextAlert} onClick={() => mutation.mutate({ status: draftStatus, ...(nextAlert ? { nextAlertId: nextAlert.alertId } : {}) })} type="button">Submit &amp; Next</button>
          </div>
          <small className="workflow-next">{nextAlert ? `Next: ${nextAlert.ruleCode} · ${nextAlert.title}` : "No other unresolved Alert matches this queue."}</small>
        </div> : <div className="read-only-note"><StatusPill value={alert.status} /><span>Status controls are hidden for VIEWER.</span></div>}</Panel>
        <Panel title="Source event" subtitle="HOT or RESTORED Event reference"><SourceEvent alert={alert} /></Panel>
        <Panel title="Connected Incidents" subtitle="Read-only correlation references">{alert.incidents.length ? <div className="link-list">{alert.incidents.map((incident) => <Link key={incident.incidentId} to={`/incidents/${incident.incidentId}`}><span><strong>{incident.title}</strong><small>{formatDateTime(incident.windowStartAt)} – {formatDateTime(incident.windowEndAt)}</small></span><span><StatusPill value={incident.severity} /><StatusPill value={incident.status} /></span></Link>)}</div> : <EmptyState title="No connected Incidents" message="This Alert is not linked to an Incident." />}</Panel>
        <Panel className="wide" title="Response guidance" subtitle="Read-only steps from the matching RuleV1 version"><ResponseGuidance steps={alert.responseGuidance} /></Panel>
      </section>
    </div>
  </section>;
}
