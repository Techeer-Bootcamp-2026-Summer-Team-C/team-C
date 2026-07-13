import { useQuery } from "@tanstack/react-query";
import { Activity, Globe2, Network, Radar } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { CountBars } from "../components/charts";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, KpiCard, PageHeader, Panel, Skeleton, StaleWarning, StatusPill } from "../components/ui";
import type { EgressTopologyDto } from "../contracts";
import { parseEndpointIds } from "../lib/endpointIds";
import { formatDateTime } from "../lib/format";
import { updateParams } from "../lib/url";

export function IntelligencePage() {
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const endpointIds = parseEndpointIds(params.get("endpointIds"));
  const summaryQuery = { ...time.query, interval: time.interval };
  const topologyQuery = { ...time.query, ...(endpointIds.length ? { endpointIds } : {}) };
  const summary = useQuery({ queryKey: ["intelligence-summary", summaryQuery], queryFn: ({ signal }) => api.dashboard(summaryQuery, signal), enabled: time.valid });
  const topology = useQuery({ queryKey: ["egress-topology", topologyQuery], queryFn: ({ signal }) => api.topology(topologyQuery, signal), enabled: time.valid });
  const error = summary.error ?? topology.error;
  return <div className="page-stack">
    <PageHeader eyebrow="THREAT INTELLIGENCE" title="Intelligence" description="MITRE mappings and Endpoint egress relationships calculated from existing Event and Alert evidence." />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}>
      <TimeFilterFields params={params} setParams={setParams} />
      <Field label="Endpoint IDs"><input onChange={(event) => setParams(updateParams(params, { endpointIds: event.target.value }))} placeholder="1, 2, 7" value={params.get("endpointIds") ?? ""} /></Field>
    </GlobalFilterBar>
    {!time.valid ? <ErrorState error={new Error("A valid custom time range is required.")} /> : null}
    {(summary.isPending || topology.isPending) && time.valid ? <Skeleton rows={10} /> : null}
    {error && !summary.data && !topology.data ? <ErrorState error={error} onRetry={() => void Promise.all([summary.refetch(), topology.refetch()])} /> : null}
    {(summary.isRefetchError || topology.isRefetchError) && summary.data && topology.data ? <StaleWarning error={error} onRetry={() => void Promise.all([summary.refetch(), topology.refetch()])} /> : null}
    {summary.data && topology.data ? <IntelligenceContent dashboard={summary.data.data} topology={topology.data.data} /> : null}
  </div>;
}

function IntelligenceContent({ dashboard, topology }: { dashboard: import("../contracts").DashboardSummaryDto; topology: EgressTopologyDto }) {
  return <>
    <section className="kpi-grid intelligence-kpis">
      <KpiCard detail="Mapped tactics" icon={<Radar size={18} />} label="MITRE tactics" value={dashboard.alerts.mitreTactics.length} />
      <KpiCard detail="Mapped techniques" icon={<Activity size={18} />} label="MITRE techniques" value={dashboard.alerts.mitreTechniques.length} />
      <KpiCard detail="Endpoints with observed egress" icon={<Network size={18} />} label="Topology nodes" value={topology.nodes.length} />
      <KpiCard detail="Unique Endpoint-to-target relationships" icon={<Globe2 size={18} />} label="Egress edges" value={topology.edges.length} />
    </section>
    <section className="overview-grid">
      <Panel title="MITRE tactics" subtitle="Alert snapshot distribution"><CountBars rows={dashboard.alerts.mitreTactics.map((row) => ({ label: `${row.mitreTacticCode} · ${row.mitreTacticName}`, count: row.count }))} /></Panel>
      <Panel title="MITRE techniques" subtitle="Alert snapshot distribution"><CountBars rows={dashboard.alerts.mitreTechniques.map((row) => ({ label: `${row.mitreTechniqueCode} · ${row.mitreTechniqueName}`, count: row.count }))} /></Panel>
      <Panel title="Top domains" subtitle="Normalized Event values"><CountBars rows={dashboard.events.topDomains.map((row) => ({ label: row.domain, count: row.count }))} /></Panel>
      <Panel title="Top remote IPs" subtitle="Normalized Event values"><CountBars rows={dashboard.events.topRemoteIps.map((row) => ({ label: row.remoteIp, count: row.count }))} /></Panel>
      <Panel title="Top processes" subtitle="Normalized Event values"><CountBars rows={dashboard.events.topProcesses.map((row) => ({ label: row.processName, count: row.count }))} /></Panel>
      <Panel className="wide" title="Endpoint egress topology" subtitle="Event and Alert counts only; traffic-byte volume is not inferred" meta={<StatusPill value="READ ONLY" />}><TopologyView topology={topology} /></Panel>
    </section>
  </>;
}

function TopologyView({ topology }: { topology: EgressTopologyDto }) {
  if (!topology.edges.length) return <EmptyState title="No egress relationships" message="No matching network, DNS, or L7 Event targets were found." />;
  return <div className="topology-stack">
    <div className="topology-nodes">{topology.nodes.map((node) => <Link className="topology-node" key={node.endpointId} to={`/endpoints/${node.endpointId}`}><span><strong>{node.hostname}</strong><small>Endpoint {node.endpointId}</small></span><span><StatusPill value={node.status} /><StatusPill value={node.riskLevel} /></span></Link>)}</div>
    <DataTable label="Endpoint egress relationships"><thead><tr><th scope="col">Source</th><th scope="col">Target</th><th scope="col">Protocol</th><th scope="col">Events</th><th scope="col">Alerts</th><th scope="col">Last seen</th></tr></thead><tbody>{topology.edges.map((edge) => <tr key={`${edge.endpointId}-${edge.target}-${edge.protocol}`}><td><Link to={`/endpoints/${edge.endpointId}`}>{edge.sourceLabel}</Link></td><td><code>{edge.target}</code></td><td>{edge.protocol}</td><td>{edge.eventCount}</td><td>{edge.alertCount}</td><td>{formatDateTime(edge.lastSeenAt)}</td></tr>)}</tbody></DataTable>
  </div>;
}
