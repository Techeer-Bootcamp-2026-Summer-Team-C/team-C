import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { DefinitionGrid, EmptyState, ErrorState, Field, PageHeader, Panel, ResponseGuidance, Skeleton, SourceEvent, StatusPill } from "../components/ui";
import type { AlertStatus } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime } from "../lib/format";
import { canMutate } from "../query/policy";

export function AlertDetailPage() {
  const { t } = useI18n();
  const alertId = Number(useParams().alertId);
  const valid = Number.isInteger(alertId) && alertId > 0;
  const auth = useAuth();
  const queryClient = useQueryClient();
  const result = useQuery({ queryKey: ["alert", alertId], queryFn: ({ signal }) => api.alert(alertId, signal), enabled: valid });
  const mutation = useMutation({
    mutationFn: (status: AlertStatus) => api.updateAlert(alertId, { status }),
    onSuccess: () => invalidateAlertData(queryClient, alertId),
  });
  if (!valid) return <ErrorState error={new Error("The Alert ID is invalid.")} />;
  return <div className="page-stack">
    <Link className="back-link" to="/alerts"><ArrowLeft aria-hidden="true" size={15} />{t("alerts.queue")}</Link>
    {result.isPending ? <Skeleton rows={10} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <AlertDetail alert={result.data.data} canUpdate={auth.user ? canMutate(auth.user.role) : false} mutation={mutation} /> : null}
  </div>;
}

export async function invalidateAlertData(queryClient: Pick<QueryClient, "invalidateQueries">, alertId: number) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["alert", alertId] }),
    queryClient.invalidateQueries({ queryKey: ["alerts"] }),
    queryClient.invalidateQueries({ queryKey: ["endpoints"] }),
  ]);
}

function AlertDetail({ alert, canUpdate, mutation }: {
  alert: import("../contracts").AlertDetailDto;
  canUpdate: boolean;
  mutation: ReturnType<typeof useMutation<import("../contracts").SuccessEnvelope<import("../contracts").AlertDto>, Error, AlertStatus>>;
}) {
  const { t } = useI18n();
  return <>
    <PageHeader eyebrow={`${alert.ruleCode} · RULE V${alert.ruleVersion}`} title={alert.title} description={alert.summary} actions={<><StatusPill value={alert.severity} /><StatusPill value={alert.status} /></>} />
    {mutation.error ? <ErrorState error={mutation.error} /> : null}
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
      <Panel title={t("alert.workflowState")} subtitle={canUpdate ? t("alert.updateAllowed") : t("alert.viewerReadOnly")}>{canUpdate ? <Field label={t("alert.status")}><select disabled={mutation.isPending} onChange={(event) => mutation.mutate(event.target.value as AlertStatus)} value={alert.status}><option>OPEN</option><option>IN_PROGRESS</option><option>RESOLVED</option></select></Field> : <div className="read-only-note"><StatusPill value={alert.status} /><span>{t("alert.viewerControlsHidden")}</span></div>}</Panel>
      <Panel title={t("alert.sourceEvent")} subtitle={t("alert.sourceEventSubtitle")}><SourceEvent alert={alert} /></Panel>
      <Panel title={t("alert.connectedIncidents")} subtitle={t("alert.correlationReferences")}>{alert.incidents.length ? <div className="link-list">{alert.incidents.map((incident) => <Link key={incident.incidentId} to={`/incidents/${incident.incidentId}`}><span><strong>{incident.title}</strong><small>{formatDateTime(incident.windowStartAt)} – {formatDateTime(incident.windowEndAt)}</small></span><span><StatusPill value={incident.severity} /><StatusPill value={incident.status} /></span></Link>)}</div> : <EmptyState title={t("alert.noConnectedIncidents")} message={t("alert.noConnectedDescription")} />}</Panel>
      <Panel className="wide" title={t("alert.responseGuidance")} subtitle={t("alert.guidanceSubtitle")}><ResponseGuidance steps={alert.responseGuidance} /></Panel>
    </section>
  </>;
}
