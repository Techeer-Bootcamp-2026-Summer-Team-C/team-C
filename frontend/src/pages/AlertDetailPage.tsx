import { useMutation, useQuery, useQueryClient, type QueryClient, type UseMutationResult } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Save } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { readTimeFilter } from "../components/filters";
import { DefinitionGrid, EmptyState, ErrorState, Field, PageHeader, Panel, ResponseGuidance, Skeleton, SourceEvent, StatusPill } from "../components/ui";
import type { AlertDto, AlertListQuery, AlertStatus, SuccessEnvelope } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { alertDetailUrl, nextActionableAlert } from "../features/alertTriage";
import { formatDateTime } from "../lib/format";
import { allowedValue, positiveInteger } from "../lib/params";
import { canMutate } from "../query/policy";

export function AlertDetailPage() {
  const { t } = useI18n();
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
    <Link className="back-link" to={backUrl}><ArrowLeft aria-hidden="true" size={15} />{t("alerts.queue")}</Link>
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
  const { t } = useI18n();
  const [draftStatus, setDraftStatus] = useState<AlertStatus>(alert.status);
  const activeQueue = queue.filter((item) => item.status !== "RESOLVED" || item.alertId === alert.alertId);
  return <section className="triage-workspace">
    <Panel className="triage-queue-panel" title={t("alert.activeQueue")} subtitle={t("alert.requiresAction", { total: queue.filter((item) => item.status !== "RESOLVED").length })}>
      {queuePending ? <Skeleton rows={8} /> : null}
      {queueError ? <ErrorState error={queueError} /> : null}
      {!queuePending && !queueError ? <div className="triage-queue" aria-label={t("alert.activeQueue")}>
        {activeQueue.map((item) => <Link
          aria-current={item.alertId === alert.alertId ? "page" : undefined}
          className={item.alertId === alert.alertId ? "triage-row selected" : "triage-row"}
          key={item.alertId}
          to={alertDetailUrl(item.alertId, params)}
        >
          <span><StatusPill value={item.severity} /><small>{t("alert.riskValue", { score: item.riskScore })}</small></span>
          <strong>{item.title}</strong>
          <code>{item.ruleCode} · {item.agentId}</code>
          <small>{formatDateTime(item.detectedAt)}</small>
        </Link>)}
        {!activeQueue.length ? <EmptyState title={t("alert.queueCleared")} message={t("alert.queueClearedDescription")} /> : null}
      </div> : null}
    </Panel>
    <div className="triage-detail page-stack">
      <PageHeader eyebrow={`${alert.ruleCode} · RULE V${alert.ruleVersion}`} title={alert.title} description={alert.summary} actions={<><StatusPill value={alert.severity} /><StatusPill value={alert.status} /></>} />
      {mutation.error ? <ErrorState error={mutation.error} /> : null}
      {mutation.isSuccess ? <div className="mutation-success"><CheckCircle2 aria-hidden="true" size={16} />{t("alert.workflowSaved")}</div> : null}
      <section className="detail-grid">
        <Panel title={t("alert.evidence")} subtitle={t("alert.detectedAt", { time: formatDateTime(alert.detectedAt) })}><DefinitionGrid items={[
          { label: t("alert.id"), value: alert.alertId },
          { label: t("alert.riskScore"), value: `${alert.riskScore} / 100` },
          { label: "Rule", value: `${alert.ruleName} · ${alert.ruleCode}` },
          { label: "Endpoint", value: <Link to={`/endpoints/${alert.endpointId}`}>Endpoint {alert.endpointId}</Link> },
          { label: t("alert.agentId"), value: <code>{alert.agentId}</code> },
          { label: t("alert.eventId"), value: <code>{alert.eventId}</code> },
          { label: t("alert.mitreTactic"), value: `${alert.mitreTacticCode} · ${alert.mitreTacticName}` },
          { label: t("alert.mitreTechnique"), value: `${alert.mitreTechniqueCode} · ${alert.mitreTechniqueName}` },
          { label: t("alert.updated"), value: formatDateTime(alert.updatedAt) },
        ]} /></Panel>
        <Panel title={t("alert.workflowState")} subtitle={canUpdate ? t("alert.saveOrContinue") : t("alert.viewerReadOnly")}>{canUpdate ? <div className="workflow-controls">
          <Field label={t("alert.status")}><select disabled={mutation.isPending} onChange={(event) => setDraftStatus(event.target.value as AlertStatus)} value={draftStatus}><option>OPEN</option><option>IN_PROGRESS</option><option>RESOLVED</option></select></Field>
          <div className="workflow-actions">
            <button className="button ghost" disabled={mutation.isPending || draftStatus === alert.status} onClick={() => mutation.mutate({ status: draftStatus })} type="button"><Save aria-hidden="true" size={15} />{t("alert.saveStatus")}</button>
            <button className="button" disabled={mutation.isPending || !nextAlert} onClick={() => mutation.mutate({ status: draftStatus, ...(nextAlert ? { nextAlertId: nextAlert.alertId } : {}) })} type="button">{t("alert.submitNext")}</button>
          </div>
          <small className="workflow-next">{nextAlert ? t("alert.nextItem", { ruleCode: nextAlert.ruleCode, title: nextAlert.title }) : t("alert.noNextItem")}</small>
        </div> : <div className="read-only-note"><StatusPill value={alert.status} /><span>{t("alert.viewerControlsHidden")}</span></div>}</Panel>
        <Panel title={t("alert.sourceEvent")} subtitle={t("alert.sourceEventSubtitle")}><SourceEvent alert={alert} /></Panel>
        <Panel title={t("alert.connectedIncidents")} subtitle={t("alert.correlationReferences")}>{alert.incidents.length ? <div className="link-list">{alert.incidents.map((incident) => <Link key={incident.incidentId} to={`/incidents/${incident.incidentId}`}><span><strong>{incident.title}</strong><small>{formatDateTime(incident.windowStartAt)} – {formatDateTime(incident.windowEndAt)}</small></span><span><StatusPill value={incident.severity} /><StatusPill value={incident.status} /></span></Link>)}</div> : <EmptyState title={t("alert.noConnectedIncidents")} message={t("alert.noConnectedDescription")} />}</Panel>
        <Panel className="wide" title={t("alert.responseGuidance")} subtitle={t("alert.guidanceSubtitle")}><ResponseGuidance steps={alert.responseGuidance} /></Panel>
      </section>
    </div>
  </section>;
}
