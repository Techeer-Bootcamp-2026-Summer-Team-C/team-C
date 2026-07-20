import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { lazy, Suspense, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { CountBars } from "../components/charts";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { Badge, Button } from "../components/primitives";
import {
  DataTable,
  DefinitionGrid,
  EmptyState,
  ErrorState,
  Field,
  GlobalFilterBar,
  Inspector,
  PageHeader,
  Panel,
  PartialFailureWarning,
  Skeleton,
  StaleWarning,
  StatusPill,
} from "../components/ui";
import type { CorrelationDto, DashboardSummaryDto, EgressTopologyDto } from "../contracts";
import {
  correlationEdgeId,
  correlationNodeId,
  endpointNodeId,
  filterTopology,
  selectedCorrelationRelationship,
  selectedTopologyEdge,
  selectedTopologyEdgeGroup,
  targetNodeId,
  topologyEdgeId,
  topologyEdgeGroupId,
  topologyGraphEnabled,
  type CorrelationSelection,
  type TopologySelection,
} from "../features/intelligenceOperations";
import { useI18n } from "../i18n/LocaleContext";
import { parseEndpointIds } from "../lib/endpointIds";
import { formatDateTime } from "../lib/format";
import { updateParams } from "../lib/url";

const LazyTopologyGraph = lazy(async () => {
  const module = await import("../components/TopologyGraph");
  return { default: module.TopologyGraph };
});

const LazyCorrelationGraph = lazy(async () => {
  const module = await import("../components/CorrelationGraph");
  return { default: module.CorrelationGraph };
});

export function IntelligencePage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const endpointIds = parseEndpointIds(params.get("endpointIds"));
  const summaryQuery = { ...time.query, interval: time.interval };
  const topologyQuery = { ...time.query, ...(endpointIds.length ? { endpointIds } : {}) };
  const correlationValue = params.get("value")?.trim() ?? "";
  const correlationRequest = { ...time.query, value: correlationValue, ...(endpointIds.length ? { endpointIds } : {}) };
  const summary = useQuery({ queryKey: ["intelligence-summary", summaryQuery], queryFn: ({ signal }) => api.dashboard(summaryQuery, signal), enabled: time.valid });
  const topology = useQuery({ queryKey: ["egress-topology", topologyQuery], queryFn: ({ signal }) => api.topology(topologyQuery, signal), enabled: time.valid });
  const correlation = useQuery({ queryKey: ["dns-correlation", correlationRequest], queryFn: ({ signal }) => api.correlation(correlationRequest, signal), enabled: time.valid && Boolean(correlationValue) });
  const summaryUnavailable = Boolean(summary.error && !summary.data);
  const topologyUnavailable = Boolean(topology.error && !topology.data);
  const error = summary.error ?? topology.error;

  return <div className="page-stack intelligence-page">
    <PageHeader title={t("intelligence.title")} />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}>
      <TimeFilterFields params={params} setParams={setParams} />
      <Field label={t("filter.endpointIds")}><input onChange={(event) => setParams(updateParams(params, { endpointIds: event.target.value }))} placeholder="1, 2, 7" value={params.get("endpointIds") ?? ""} /></Field>
    </GlobalFilterBar>
    {!time.valid ? <ErrorState error={new Error(t("filter.invalidRange"))} /> : null}
    {time.valid && !summary.data && !topology.data && (summary.isPending || topology.isPending) ? <Skeleton rows={10} /> : null}
    {summaryUnavailable && topologyUnavailable ? <ErrorState error={error} onRetry={() => void Promise.all([summary.refetch(), topology.refetch()])} /> : null}
    {(summaryUnavailable !== topologyUnavailable) ? <PartialFailureWarning message={summaryUnavailable ? t("intelligence.summaryUnavailable") : t("intelligence.topologyUnavailable")} /> : null}
    {(summary.isRefetchError || topology.isRefetchError) && (summary.data || topology.data) ? <StaleWarning error={error} onRetry={() => void Promise.all([summary.refetch(), topology.refetch()])} /> : null}
    {(summary.data || topology.data) ? <IntelligenceContent dashboard={summary.data?.data ?? null} topology={topology.data?.data ?? null} /> : null}
    {time.valid ? <CorrelationWorkspace
      correlation={correlation.data?.data ?? null}
      error={correlation.error}
      graphEnabled={topologyGraphEnabled()}
      isPending={correlation.isPending && Boolean(correlationValue)}
      isRefetchError={correlation.isRefetchError}
      onRetry={() => void correlation.refetch()}
      onSearch={(value) => {
        const nextValue = value.trim();
        if (nextValue && nextValue === correlationValue) void correlation.refetch();
        else setParams(updateParams(params, { value: nextValue }));
      }}
      suggestions={summary.data ? [
        ...summary.data.data.events.topDomains.slice(0, 3).map((row) => row.domain),
        ...summary.data.data.events.topRemoteIps.slice(0, 3).map((row) => row.remoteIp),
      ] : []}
      value={correlationValue}
      key={correlationValue}
    /> : null}
  </div>;
}

export function CorrelationWorkspace({
  value,
  correlation,
  suggestions,
  graphEnabled,
  isPending,
  isRefetchError,
  error,
  onSearch,
  onRetry,
}: {
  value: string;
  correlation: CorrelationDto | null;
  suggestions: string[];
  graphEnabled: boolean;
  isPending: boolean;
  isRefetchError: boolean;
  error: Error | null;
  onSearch: (value: string) => void;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState(value);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSearch(draft.trim());
  };

  return <Panel className="correlation-workspace-panel" title={t("intelligence.correlationTitle")} subtitle={t("intelligence.correlationSubtitle")} meta={<StatusPill value="READ ONLY" />}>
    <form className="correlation-toolbar" onSubmit={submit}>
      <Field label={t("intelligence.correlationValue")}><span className="search-field"><Search aria-hidden="true" size={15} /><input aria-label={t("intelligence.correlationValue")} onChange={(event) => setDraft(event.target.value)} placeholder={t("intelligence.correlationPlaceholder")} type="search" value={draft} /></span></Field>
      <Button disabled={!draft.trim()} type="submit" variant="primary">{t("intelligence.lookup")}</Button>
    </form>
    {suggestions.length ? <div className="correlation-suggestions"><span>{t("intelligence.tryObservedSignal")}</span>{[...new Set(suggestions)].map((suggestion) => <button key={suggestion} onClick={() => { setDraft(suggestion); onSearch(suggestion); }} type="button"><code>{suggestion}</code></button>)}</div> : null}
    {!value ? <EmptyState title={t("intelligence.correlationReady")} message={t("intelligence.correlationReadyDescription")} /> : null}
    {value && isPending ? <Skeleton rows={8} /> : null}
    {value && error && !correlation ? <ErrorState error={error} onRetry={onRetry} /> : null}
    {correlation && isRefetchError ? <StaleWarning error={error} onRetry={onRetry} /> : null}
    {correlation ? <CorrelationResult correlation={correlation} graphEnabled={graphEnabled} key={`${correlation.inputType}:${correlation.inputValue}`} /> : null}
  </Panel>;
}

export function CorrelationResult({ correlation, graphEnabled }: { correlation: CorrelationDto; graphEnabled: boolean }) {
  const { t } = useI18n();
  const [selection, setSelection] = useState<CorrelationSelection | null>(null);
  if (!correlation.relationships.length) return <EmptyState title={t("intelligence.noCorrelation")} message={t("intelligence.noCorrelationDescription")} />;

  return <>
    <div className="correlation-summary" role="status">
      <span><strong>{correlation.inputType}</strong><code>{correlation.inputValue}</code></span>
      <span>{t("intelligence.relatedCount", { count: correlation.related.length })}</span>
      <span>{formatDateTime(correlation.from)} — {formatDateTime(correlation.to)}</span>
    </div>
    <div className="topology-stage correlation-stage">
      <aside aria-label={t("intelligence.correlationLegend")} className="topology-legend"><strong>{t("intelligence.correlationLegend")}</strong><ul><li><i className="correlation-input" />{t("intelligence.inputNode")}</li><li><i className="domain" />Domain</li><li><i className="ip" />IP</li><li><i className="live" />LIVE_DNS</li><li><i className="observed" />OBSERVED_EVENTS</li></ul><small>{t("intelligence.ptrCaveat")}</small></aside>
      {graphEnabled ? <Suspense fallback={<Skeleton rows={8} />}><LazyCorrelationGraph correlation={correlation} label={t("intelligence.correlationGraphAria")} onSelect={setSelection} selection={selection} /></Suspense> : <div className="topology-fallback" role="status"><Badge tone="neutral">{t("intelligence.tableFallback")}</Badge><strong>{t("intelligence.correlationGraphDisabled")}</strong><p>{t("intelligence.correlationGraphDisabledDescription")}</p></div>}
      <CorrelationInspector correlation={correlation} selection={selection} />
    </div>
    <CorrelationEvidenceTable correlation={correlation} onSelect={setSelection} selection={selection} />
  </>;
}

function CorrelationInspector({ correlation, selection }: { correlation: CorrelationDto; selection: CorrelationSelection | null }) {
  const { t } = useI18n();
  const edge = selectedCorrelationRelationship(correlation, selection);
  if (edge) return <Inspector actions={<Badge tone={edge.sources.includes("LIVE_DNS") ? "info" : "neutral"}>{edge.sources.join(" + ")}</Badge>} description={`${edge.sourceValue} → ${edge.targetValue}`} title={edge.relation.replaceAll("_", " ")}>
    <DefinitionGrid items={[
      { label: t("intelligence.source"), value: `${edge.sourceType} · ${edge.sourceValue}` },
      { label: t("intelligence.target"), value: `${edge.targetType} · ${edge.targetValue}` },
      { label: t("intelligence.evidenceSource"), value: edge.sources.join(", ") },
    ]} />
  </Inspector>;
  if (selection?.kind === "NODE") {
    const node = correlation.related.find((item) => correlationNodeId(item.valueType, item.value) === selection.id)
      ?? (correlationNodeId(correlation.inputType, correlation.inputValue) === selection.id ? { value: correlation.inputValue, valueType: correlation.inputType, sources: [] } : null);
    if (node) return <Inspector description={node.valueType === "IP" ? t("intelligence.ipNodeDescription") : t("intelligence.domainNodeDescription")} title={node.value}>
      <DefinitionGrid items={[
        { label: t("intelligence.nodeType"), value: node.valueType },
        { label: t("intelligence.evidenceSource"), value: node.sources.length ? node.sources.join(", ") : t("intelligence.inputNode") },
        { label: t("intelligence.relationships"), value: correlation.relationships.filter((edgeItem) => correlationNodeId(edgeItem.sourceType, edgeItem.sourceValue) === selection.id || correlationNodeId(edgeItem.targetType, edgeItem.targetValue) === selection.id).length },
      ]} />
    </Inspector>;
  }
  return <Inspector description={t("intelligence.correlationSelectPrompt")} title={t("intelligence.selectedContext")}><EmptyState title={t("intelligence.nothingSelected")} message={t("intelligence.correlationSelectPrompt")} /></Inspector>;
}

function CorrelationEvidenceTable({ correlation, selection, onSelect }: { correlation: CorrelationDto; selection: CorrelationSelection | null; onSelect: (selection: CorrelationSelection) => void }) {
  const { t } = useI18n();
  return <DataTable className="relationship-evidence-table" label={t("intelligence.correlationTable")}><thead><tr><th scope="col">{t("intelligence.source")}</th><th scope="col">{t("intelligence.relationship")}</th><th scope="col">{t("intelligence.target")}</th><th scope="col">{t("intelligence.evidenceSource")}</th></tr></thead><tbody>{correlation.relationships.map((edge) => {
    const id = correlationEdgeId(edge);
    const selected = selection?.kind === "EDGE" && selection.id === id;
    return <tr className={selected ? "selected-row" : undefined} key={id}><td><button aria-pressed={selected} className="evidence-select" onClick={() => onSelect({ kind: "EDGE", id })} type="button"><code>{edge.sourceValue}</code></button></td><td>{edge.relation}</td><td><code>{edge.targetValue}</code></td><td>{edge.sources.map((source) => <Badge key={source} tone={source === "LIVE_DNS" ? "info" : "neutral"}>{source}</Badge>)}</td></tr>;
  })}</tbody></DataTable>;
}

export function IntelligenceContent({
  dashboard,
  topology,
  graphEnabled = topologyGraphEnabled(),
}: {
  dashboard: DashboardSummaryDto | null;
  topology: EgressTopologyDto | null;
  graphEnabled?: boolean;
}) {
  const { t } = useI18n();
  return <>
    <section aria-label={t("intelligence.title")} className="intelligence-summary-rail">
      {dashboard ? <>
        <article><span>{t("intelligence.mitreTactics")}</span><strong>{dashboard.alerts.mitreTactics.length}</strong><small>{t("intelligence.mappedTactics")}</small></article>
        <article><span>{t("intelligence.mitreTechniques")}</span><strong>{dashboard.alerts.mitreTechniques.length}</strong><small>{t("intelligence.mappedTechniques")}</small></article>
      </> : null}
      {topology ? <>
        <article><span>{t("intelligence.topologyNodes")}</span><strong>{topology.nodes.length}</strong><small>{t("intelligence.observedEgress")}</small></article>
        <article><span>{t("intelligence.egressEdges")}</span><strong>{topology.edges.length}</strong><small>{t("intelligence.uniqueRelationships")}</small></article>
      </> : null}
    </section>
    {dashboard ? <MitreAndSignals dashboard={dashboard} /> : null}
    {topology ? <TopologyWorkspace graphEnabled={graphEnabled} topology={topology} /> : null}
  </>;
}

type MitreSelection = { type: "TACTIC" | "TECHNIQUE"; code: string; name: string; count: number };

function MitreAndSignals({ dashboard }: { dashboard: DashboardSummaryDto }) {
  const { t } = useI18n();
  const [selection, setSelection] = useState<MitreSelection | null>(null);
  const [topTab, setTopTab] = useState<"RULES" | "SIGNALS">("RULES");
  const tactics = dashboard.alerts.mitreTactics.slice(0, 10);
  const techniques = dashboard.alerts.mitreTechniques.slice(0, 10);
  const signalRows = [
    ...dashboard.events.topDomains.map((row) => ({ label: `Domain · ${row.domain}`, count: row.count })),
    ...dashboard.events.topRemoteIps.map((row) => ({ label: `IP · ${row.remoteIp}`, count: row.count })),
    ...dashboard.events.topProcesses.map((row) => ({ label: `Process · ${row.processName}`, count: row.count })),
  ].sort((left, right) => right.count - left.count).slice(0, 10);

  return <section className="intelligence-analysis-grid">
    <Panel className="mitre-workspace" title={t("intelligence.mitreMatrix")}>
      <div className="mitre-status-strip" role="status">
        <div><span>{t("intelligence.observedTactics")}</span><strong>{tactics.length}</strong></div>
        <div><span>{t("intelligence.observedTechniques")}</span><strong>{techniques.length}</strong></div>
        <div className="mitre-coverage-gap"><Badge tone="neutral">{t("intelligence.coverageUnavailable")}</Badge><small>{t("intelligence.coverageUnavailableDescription")}</small></div>
      </div>
      <div className="mitre-layout">
        <div className="mitre-matrix" aria-label={t("intelligence.mitreMatrix")}>
          <MitreGroup label={t("intelligence.mitreTactics")} rows={tactics.map((row) => ({ type: "TACTIC" as const, code: row.mitreTacticCode, name: row.mitreTacticName, count: row.count }))} selection={selection} onSelect={setSelection} />
          <MitreGroup label={t("intelligence.mitreTechniques")} rows={techniques.map((row) => ({ type: "TECHNIQUE" as const, code: row.mitreTechniqueCode, name: row.mitreTechniqueName, count: row.count }))} selection={selection} onSelect={setSelection} />
        </div>
        <Inspector description={selection ? `${selection.code} · ${selection.type}` : t("intelligence.mitreSelectPrompt")} title={selection?.name ?? t("intelligence.selectedContext")}>
          {selection ? <DefinitionGrid items={[
            { label: t("intelligence.mappingType"), value: selection.type },
            { label: t("intelligence.mappingCode"), value: selection.code },
            { label: t("intelligence.alertCount"), value: selection.count },
            { label: t("intelligence.timeRange"), value: `${formatDateTime(dashboard.timeRange.from)} — ${formatDateTime(dashboard.timeRange.to)}` },
          ]} /> : <EmptyState title={t("intelligence.nothingSelected")} message={t("intelligence.mitreSelectPrompt")} />}
        </Inspector>
      </div>
      <details className="table-fallback"><summary>{t("intelligence.openTableFallback")}</summary>
        <DataTable label={t("intelligence.mitreTableFallback")}><thead><tr><th scope="col">Type</th><th scope="col">Code</th><th scope="col">Name</th><th scope="col">Alerts</th></tr></thead><tbody>
          {[...tactics.map((row) => ({ type: "TACTIC", code: row.mitreTacticCode, name: row.mitreTacticName, count: row.count })), ...techniques.map((row) => ({ type: "TECHNIQUE", code: row.mitreTechniqueCode, name: row.mitreTechniqueName, count: row.count }))].map((row) => <tr key={`${row.type}-${row.code}`}><td>{row.type}</td><td><code>{row.code}</code></td><td>{row.name}</td><td>{row.count}</td></tr>)}
        </tbody></DataTable>
      </details>
    </Panel>
    <Panel title={t("intelligence.rulesSignals")} subtitle={t("intelligence.topNSubtitle")}>
      <div aria-label={t("intelligence.rulesSignals")} className="tabs" role="tablist">
        {(["RULES", "SIGNALS"] as const).map((tab) => <button aria-selected={topTab === tab} className={topTab === tab ? "active" : undefined} key={tab} onClick={() => setTopTab(tab)} role="tab" type="button">{tab === "RULES" ? t("intelligence.rules") : t("intelligence.signals")}</button>)}
      </div>
      <div aria-label={topTab === "RULES" ? t("intelligence.rules") : t("intelligence.signals")} className="tab-panel" role="tabpanel">
        {topTab === "RULES" ? <CountBars rows={dashboard.alerts.topRules.slice(0, 10).map((row) => ({ label: `${row.ruleCode} · ${row.ruleName}`, count: row.count }))} /> : <CountBars rows={signalRows} />}
      </div>
    </Panel>
  </section>;
}

function MitreGroup({
  label,
  rows,
  selection,
  onSelect,
}: {
  label: string;
  rows: MitreSelection[];
  selection: MitreSelection | null;
  onSelect: (selection: MitreSelection) => void;
}) {
  const { t } = useI18n();
  const maximum = Math.max(...rows.map((row) => row.count), 0);
  return <section><h3>{label}</h3>{rows.length ? <div className="mitre-cells">{rows.map((row) => {
    const selected = selection?.type === row.type && selection.code === row.code;
    const heat = maximum > 0 ? Math.max(1, Math.ceil((row.count / maximum) * 3)) : 0;
    return <button aria-pressed={selected} className={`${selected ? "selected " : ""}heat-${heat}`.trim()} key={`${row.type}-${row.code}`} onClick={() => onSelect(row)} type="button"><code>{row.code}</code><strong>{row.name}</strong><span>{t("intelligence.alertsCount", { count: row.count })}</span></button>;
  })}</div> : <EmptyState title={t("intelligence.noMappings")} message={t("intelligence.noMappingsDescription")} />}</section>;
}

export function TopologyWorkspace({ topology, graphEnabled }: { topology: EgressTopologyDto; graphEnabled: boolean }) {
  const { t } = useI18n();
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(10);
  const [selection, setSelection] = useState<TopologySelection | null>(null);
  const filtered = useMemo(() => filterTopology(topology, search, limit), [topology, search, limit]);
  if (!topology.edges.length) return <Panel title={t("intelligence.egressTopology")} subtitle={t("intelligence.egressSubtitle")}><EmptyState title={t("intelligence.noRelationships")} message={t("intelligence.noRelationshipsDescription")} /></Panel>;

  return <Panel className="topology-workspace-panel" title={t("intelligence.egressTopology")} subtitle={t("intelligence.egressSubtitle")} meta={<StatusPill value="READ ONLY" />}>
    <div className="topology-toolbar">
      <Field label={t("intelligence.searchTopology")}><span className="search-field"><Search aria-hidden="true" size={15} /><input onChange={(event) => setSearch(event.target.value)} type="search" value={search} /></span></Field>
      <Field label={t("intelligence.topN")}><select onChange={(event) => setLimit(Number(event.target.value))} value={limit}><option value={10}>10</option><option value={25}>25</option><option value={50}>50</option></select></Field>
      <span className="topology-range">{formatDateTime(topology.from)} — {formatDateTime(topology.to)}</span>
    </div>
    {!filtered.edges.length ? <EmptyState title={t("intelligence.noFilteredRelationships")} message={t("intelligence.noFilteredRelationshipsDescription")} /> : <>
      <div className="topology-stage">
        <aside aria-label={t("intelligence.legend")} className="topology-legend"><strong>{t("intelligence.legend")}</strong><ul><li><i className="endpoint" />Endpoint</li><li><i className="target" />Target</li><li><i className="observed" />{t("intelligence.observedEdge")}</li></ul><small>{t("intelligence.countsNotTraffic")}</small></aside>
        {graphEnabled ? <Suspense fallback={<Skeleton rows={8} />}><LazyTopologyGraph label={t("intelligence.graphAria")} onSelect={setSelection} selection={selection} topology={filtered} /></Suspense> : <div className="topology-fallback" role="status"><Badge tone="neutral">{t("intelligence.tableFallback")}</Badge><strong>{t("intelligence.graphDisabled")}</strong><p>{t("intelligence.graphDisabledDescription")}</p></div>}
        <TopologyInspector selection={selection} topology={filtered} />
      </div>
      <TopologyEvidenceTable onSelect={setSelection} selection={selection} topology={filtered} />
    </>}
  </Panel>;
}

function TopologyInspector({ topology, selection }: { topology: EgressTopologyDto; selection: TopologySelection | null }) {
  const { t } = useI18n();
  const edgeGroup = selectedTopologyEdgeGroup(topology, selection);
  if (edgeGroup) return <Inspector description={`${edgeGroup.sourceLabel} → ${edgeGroup.target}`} title={`${edgeGroup.protocols.join(" + ")} ${t("intelligence.relationship")}`}>
    <DefinitionGrid items={[
      { label: "Protocols", value: edgeGroup.protocols.join(", ") },
      { label: t("intelligence.eventCount"), value: edgeGroup.eventCount },
      { label: t("intelligence.alertCount"), value: edgeGroup.alertCount },
      { label: t("intelligence.lastObserved"), value: formatDateTime(edgeGroup.lastSeenAt) },
    ]} />
    <div className="context-links"><Link to={evidenceListUrl("events", edgeGroup, topology)}>Events</Link><Link to={evidenceListUrl("alerts", edgeGroup, topology)}>Alerts</Link></div>
  </Inspector>;
  const edge = selectedTopologyEdge(topology, selection);
  if (edge) return <Inspector description={`${edge.sourceLabel} → ${edge.target}`} title={`${edge.protocol} ${t("intelligence.relationship")}`}>
    <DefinitionGrid items={[
      { label: "Protocol", value: edge.protocol },
      { label: t("intelligence.eventCount"), value: edge.eventCount },
      { label: t("intelligence.alertCount"), value: edge.alertCount },
      { label: t("intelligence.lastObserved"), value: formatDateTime(edge.lastSeenAt) },
    ]} />
    <div className="context-links"><Link to={evidenceListUrl("events", edge, topology)}>Events</Link><Link to={evidenceListUrl("alerts", edge, topology)}>Alerts</Link></div>
  </Inspector>;
  if (selection?.kind === "NODE") {
    const endpoint = topology.nodes.find((node) => endpointNodeId(node.endpointId) === selection.id);
    if (endpoint) return <Inspector actions={<StatusPill value={endpoint.riskLevel} />} description={`Endpoint ${endpoint.endpointId}`} title={endpoint.hostname}>
      <DefinitionGrid items={[{ label: "Risk", value: endpoint.riskScore }, { label: t("filter.status"), value: endpoint.status }, { label: t("intelligence.alertCount"), value: endpoint.alertCount }]} />
      <div className="context-links"><Link to={`/endpoints/${endpoint.endpointId}`}>{t("intelligence.openEndpoint")}</Link></div>
    </Inspector>;
    if (selection.id.startsWith("target:")) return <Inspector description={t("intelligence.observedTargetDescription")} title={selection.id.slice(7)}><DefinitionGrid items={[{ label: t("intelligence.nodeType"), value: "TARGET" }, { label: t("intelligence.relationships"), value: topology.edges.filter((item) => targetNodeId(item.target) === selection.id).length }]} /></Inspector>;
  }
  return <Inspector description={t("intelligence.topologySelectPrompt")} title={t("intelligence.selectedContext")}><EmptyState title={t("intelligence.nothingSelected")} message={t("intelligence.topologySelectPrompt")} /></Inspector>;
}

function TopologyEvidenceTable({ topology, selection, onSelect }: { topology: EgressTopologyDto; selection: TopologySelection | null; onSelect: (selection: TopologySelection) => void }) {
  const { t } = useI18n();
  return <DataTable className="relationship-evidence-table" label={t("intelligence.relationships")}><thead><tr><th scope="col">{t("intelligence.source")}</th><th scope="col">{t("intelligence.target")}</th><th scope="col">Protocol</th><th scope="col">Events</th><th scope="col">Alerts</th><th scope="col">{t("intelligence.lastObserved")}</th></tr></thead><tbody>{topology.edges.map((edge) => {
    const id = topologyEdgeId(edge.endpointId, edge.target, edge.protocol);
    const selected = (selection?.kind === "EDGE" && selection.id === id)
      || (selection?.kind === "EDGE_GROUP" && selection.id === topologyEdgeGroupId(edge.endpointId, edge.target));
    return <tr className={selected ? "selected-row" : undefined} key={id}><td><button aria-pressed={selected} className="evidence-select" onClick={() => onSelect({ kind: "EDGE", id })} type="button">{edge.sourceLabel}</button></td><td><code>{edge.target}</code></td><td>{edge.protocol}</td><td><Link to={evidenceListUrl("events", edge, topology)}>{edge.eventCount}</Link></td><td><Link to={evidenceListUrl("alerts", edge, topology)}>{edge.alertCount}</Link></td><td>{formatDateTime(edge.lastSeenAt)}</td></tr>;
  })}</tbody></DataTable>;
}

function evidenceListUrl(route: "events" | "alerts", edge: { endpointId: number }, topology: EgressTopologyDto): string {
  const query = new URLSearchParams({ from: topology.from, to: topology.to });
  query.set(route === "events" ? "endpointIds" : "endpointId", String(edge.endpointId));
  return `/${route}?${query.toString()}`;
}
