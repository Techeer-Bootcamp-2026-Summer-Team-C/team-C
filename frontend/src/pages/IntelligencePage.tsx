import { useQuery } from "@tanstack/react-query";
import { Activity, Globe2, Network, Radar } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { CountBars } from "../components/charts";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, KpiCard, PageHeader, Panel, Skeleton, StaleWarning, StatusPill } from "../components/ui";
import type { EgressTopologyDto } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { parseEndpointIds } from "../lib/endpointIds";
import { formatDateTime } from "../lib/format";
import { updateParams } from "../lib/url";

export function IntelligencePage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const endpointIds = parseEndpointIds(params.get("endpointIds"));
  const summaryQuery = { ...time.query, interval: time.interval };
  const topologyQuery = { ...time.query, ...(endpointIds.length ? { endpointIds } : {}) };
  const summary = useQuery({ queryKey: ["intelligence-summary", summaryQuery], queryFn: ({ signal }) => api.dashboard(summaryQuery, signal), enabled: time.valid });
  const topology = useQuery({ queryKey: ["egress-topology", topologyQuery], queryFn: ({ signal }) => api.topology(topologyQuery, signal), enabled: time.valid });
  const error = summary.error ?? topology.error;
  return <div className="page-stack">
    <PageHeader eyebrow="THREAT INTELLIGENCE" title={t("intelligence.title")} description={t("intelligence.description")} />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}>
      <TimeFilterFields params={params} setParams={setParams} />
      <Field label={t("filter.endpointIds")}><input onChange={(event) => setParams(updateParams(params, { endpointIds: event.target.value }))} placeholder="1, 2, 7" value={params.get("endpointIds") ?? ""} /></Field>
    </GlobalFilterBar>
    {!time.valid ? <ErrorState error={new Error(t("filter.invalidRange"))} /> : null}
    {(summary.isPending || topology.isPending) && time.valid ? <Skeleton rows={10} /> : null}
    {error && !summary.data && !topology.data ? <ErrorState error={error} onRetry={() => void Promise.all([summary.refetch(), topology.refetch()])} /> : null}
    {(summary.isRefetchError || topology.isRefetchError) && summary.data && topology.data ? <StaleWarning error={error} onRetry={() => void Promise.all([summary.refetch(), topology.refetch()])} /> : null}
    {summary.data && topology.data ? <IntelligenceContent dashboard={summary.data.data} topology={topology.data.data} /> : null}
  </div>;
}

function IntelligenceContent({ dashboard, topology }: { dashboard: import("../contracts").DashboardSummaryDto; topology: EgressTopologyDto }) {
  const { t } = useI18n();
  return <>
    <section className="kpi-grid intelligence-kpis">
      <KpiCard detail={t("intelligence.mappedTactics")} icon={<Radar size={18} />} label={t("intelligence.mitreTactics")} value={dashboard.alerts.mitreTactics.length} />
      <KpiCard detail={t("intelligence.mappedTechniques")} icon={<Activity size={18} />} label={t("intelligence.mitreTechniques")} value={dashboard.alerts.mitreTechniques.length} />
      <KpiCard detail={t("intelligence.observedEgress")} icon={<Network size={18} />} label={t("intelligence.topologyNodes")} value={topology.nodes.length} />
      <KpiCard detail={t("intelligence.uniqueRelationships")} icon={<Globe2 size={18} />} label={t("intelligence.egressEdges")} value={topology.edges.length} />
    </section>
    <section className="overview-grid">
      <Panel title={t("intelligence.mitreTactics")} subtitle={t("intelligence.alertDistribution")}><CountBars rows={dashboard.alerts.mitreTactics.map((row) => ({ label: `${row.mitreTacticCode} · ${row.mitreTacticName}`, count: row.count }))} /></Panel>
      <Panel title={t("intelligence.mitreTechniques")} subtitle={t("intelligence.alertDistribution")}><CountBars rows={dashboard.alerts.mitreTechniques.map((row) => ({ label: `${row.mitreTechniqueCode} · ${row.mitreTechniqueName}`, count: row.count }))} /></Panel>
      <Panel title={t("intelligence.topDomains")} subtitle={t("intelligence.normalizedValues")}><CountBars rows={dashboard.events.topDomains.map((row) => ({ label: row.domain, count: row.count }))} /></Panel>
      <Panel title={t("intelligence.topRemoteIps")} subtitle={t("intelligence.normalizedValues")}><CountBars rows={dashboard.events.topRemoteIps.map((row) => ({ label: row.remoteIp, count: row.count }))} /></Panel>
      <Panel title={t("intelligence.topProcesses")} subtitle={t("intelligence.normalizedValues")}><CountBars rows={dashboard.events.topProcesses.map((row) => ({ label: row.processName, count: row.count }))} /></Panel>
      <Panel className="wide" title={t("intelligence.egressTopology")} subtitle={t("intelligence.egressSubtitle")} meta={<StatusPill value="READ ONLY" />}><TopologyView topology={topology} /></Panel>
    </section>
  </>;
}

function TopologyView({ topology }: { topology: EgressTopologyDto }) {
  const { t } = useI18n();
  if (!topology.edges.length) return <EmptyState title={t("intelligence.noRelationships")} message={t("intelligence.noRelationshipsDescription")} />;
  return <div className="topology-stack">
    <div className="topology-nodes">{topology.nodes.map((node) => <Link className="topology-node" key={node.endpointId} to={`/endpoints/${node.endpointId}`}><span><strong>{node.hostname}</strong><small>Endpoint {node.endpointId}</small></span><span><StatusPill value={node.status} /><StatusPill value={node.riskLevel} /></span></Link>)}</div>
    <DataTable label={t("intelligence.relationships")}><thead><tr><th scope="col">{t("intelligence.source")}</th><th scope="col">{t("intelligence.target")}</th><th scope="col">Protocol</th><th scope="col">Events</th><th scope="col">Alerts</th><th scope="col">{t("endpoints.lastSeen")}</th></tr></thead><tbody>{topology.edges.map((edge) => <tr key={`${edge.endpointId}-${edge.target}-${edge.protocol}`}><td><Link to={`/endpoints/${edge.endpointId}`}>{edge.sourceLabel}</Link></td><td><code>{edge.target}</code></td><td>{edge.protocol}</td><td>{edge.eventCount}</td><td>{edge.alertCount}</td><td>{formatDateTime(edge.lastSeenAt)}</td></tr>)}</tbody></DataTable>
  </div>;
}
