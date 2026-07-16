import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import type {
  IncidentInvestigationDto,
  InvestigationEdgeDto,
  InvestigationNodeDto,
} from "../contracts";
import {
  graphRequiresFallback,
  incidentGraphEnabled,
  selectedEdge,
  selectedNode,
  selectionNodeIds,
  type InvestigationSelection,
} from "../features/incidentInvestigation";
import { useI18n } from "../i18n/LocaleContext";
import { displayNullable, formatDateTime, humanize } from "../lib/format";
import { Badge } from "./primitives";
import { DataTable, DefinitionGrid, EmptyState, Inspector, Panel, PartialFailureWarning, Skeleton, StatusPill } from "./ui";

const LazyIncidentGraph = lazy(async () => {
  const module = await import("./IncidentGraph");
  return { default: module.IncidentGraph };
});

const NODE_TYPES = ["INCIDENT", "ALERT", "EVENT", "PROCESS", "DESTINATION"] as const;

export function IncidentInvestigation({
  investigation,
  selection,
  onSelect,
  graphEnabled = incidentGraphEnabled(),
}: {
  investigation: IncidentInvestigationDto;
  selection: InvestigationSelection | null;
  onSelect: (selection: InvestigationSelection) => void;
  graphEnabled?: boolean;
}) {
  const { t } = useI18n();
  const fallback = graphRequiresFallback(investigation);
  const showGraph = graphEnabled && !fallback;
  const counts = new Map(NODE_TYPES.map((type) => [type, investigation.nodes.filter((node) => node.nodeType === type).length]));

  return <div className="investigation-stack">
    {investigation.partial || investigation.truncated ? <PartialFailureWarning message={t("incident.investigationPartial")} /> : null}
    {investigation.warnings.length ? <ul aria-label={t("incident.investigationWarnings")} className="investigation-warnings">{investigation.warnings.map((warning, index) => <li key={`${warning.code}-${warning.eventId ?? index}`}>
      <StatusPill value={warning.code} /><span>{warning.message}</span>{warning.code === "ARCHIVE_NOT_READY" ? <Link to="/operations/archives">{t("error.archiveAction")}</Link> : null}
    </li>)}</ul> : null}
    <Panel className="investigation-panel" title={t("incident.investigation")} subtitle={t("incident.investigationSubtitle")} meta={<Badge tone="info">{t("incident.observedOnly")}</Badge>}>
      <div className="investigation-stage">
        <aside aria-label={t("incident.legend")} className="investigation-legend">
          <strong>{t("incident.legend")}</strong>
          <ul>{NODE_TYPES.map((type) => <li key={type}><i className={`legend-${type.toLowerCase()}`} /><span>{humanize(type)}</span><b>{counts.get(type)}</b></li>)}</ul>
          <div><span>{t("incident.edges")}</span><b>{investigation.edgeCount}</b></div>
        </aside>
        {showGraph ? <Suspense fallback={<Skeleton rows={8} />}><LazyIncidentGraph investigation={investigation} onSelect={onSelect} selection={selection} /></Suspense>
          : <GraphFallback enabled={graphEnabled} investigation={investigation} />}
        <SelectedContext investigation={investigation} selection={selection} />
      </div>
    </Panel>
    <EvidenceTable investigation={investigation} onSelect={onSelect} selection={selection} />
  </div>;
}

function GraphFallback({ enabled, investigation }: { enabled: boolean; investigation: IncidentInvestigationDto }) {
  const { t } = useI18n();
  const title = !enabled ? t("incident.graphDisabled")
    : investigation.nodes.length === 0 ? t("incident.graphEmpty")
      : t("incident.graphIncomplete");
  return <div className="investigation-fallback" role="status">
    <Badge tone={investigation.partial || investigation.truncated ? "warning" : "neutral"}>{t("incident.tableFallback")}</Badge>
    <strong>{title}</strong>
    <p>{t("incident.graphFallbackDescription")}</p>
  </div>;
}

function SelectedContext({ investigation, selection }: { investigation: IncidentInvestigationDto; selection: InvestigationSelection | null }) {
  const { t } = useI18n();
  const node = selectedNode(selection, investigation);
  const edge = selectedEdge(selection, investigation);
  if (!node && !edge) return <Inspector description={t("incident.selectedPrompt")} title={t("incident.selectedContext")}><EmptyState title={t("incident.nothingSelected")} message={t("incident.selectedPrompt")} /></Inspector>;
  if (node) return <Inspector actions={<StatusPill value={node.nodeType} />} description={node.nodeId} title={node.label}>
    <DefinitionGrid items={nodeDefinitionItems(node, t)} />
    <NodeLinks node={node} />
  </Inspector>;
  const source = investigation.nodes.find((candidate) => candidate.nodeId === edge!.sourceNodeId);
  const target = investigation.nodes.find((candidate) => candidate.nodeId === edge!.targetNodeId);
  return <Inspector actions={<Badge tone="success">{edge!.evidence}</Badge>} description={t("incident.observedRelationDescription")} title={humanize(edge!.relation)}>
    <DefinitionGrid items={[
      { label: t("incident.source"), value: source?.label ?? edge!.sourceNodeId },
      { label: t("incident.target"), value: target?.label ?? edge!.targetNodeId },
      { label: t("incident.relation"), value: edge!.relation },
      { label: t("incident.evidence"), value: edge!.evidence },
      { label: t("incident.observedAt"), value: formatDateTime(edge!.observedAt) },
    ]} />
    <EvidenceLinks edge={edge!} investigation={investigation} />
  </Inspector>;
}

function EvidenceTable({
  investigation,
  selection,
  onSelect,
}: {
  investigation: IncidentInvestigationDto;
  selection: InvestigationSelection | null;
  onSelect: (selection: InvestigationSelection) => void;
}) {
  const { t } = useI18n();
  if (!investigation.edges.length) return <Panel title={t("incident.evidenceList")} subtitle={t("incident.evidenceSubtitle")}><EmptyState title={t("incident.noGraphEvidence")} message={t("incident.graphFallbackDescription")} /></Panel>;
  const nodeById = new Map(investigation.nodes.map((node) => [node.nodeId, node]));
  const selectedIds = selectionNodeIds(selection, investigation);
  return <Panel title={t("incident.evidenceList")} subtitle={t("incident.evidenceSubtitle")} meta={<Badge tone="success">OBSERVED</Badge>}>
    <DataTable label={t("incident.evidenceList")}><thead><tr><th scope="col">{t("incident.relation")}</th><th scope="col">{t("incident.source")}</th><th scope="col">{t("incident.target")}</th><th scope="col">{t("incident.evidence")}</th><th scope="col">{t("incident.observedAt")}</th><th scope="col">{t("incident.sourceRecord")}</th></tr></thead><tbody>
      {investigation.edges.map((edge) => {
        const selected = selection?.kind === "EDGE" && selection.id === edge.edgeId;
        const connected = selectedIds.has(edge.sourceNodeId) || selectedIds.has(edge.targetNodeId);
        return <tr className={selected || connected ? "selected-row" : undefined} key={edge.edgeId}>
          <td><button aria-pressed={selected} className="evidence-select" onClick={() => onSelect({ kind: "EDGE", id: edge.edgeId })} type="button">{humanize(edge.relation)}</button></td>
          <td>{nodeById.get(edge.sourceNodeId)?.label ?? edge.sourceNodeId}</td>
          <td>{nodeById.get(edge.targetNodeId)?.label ?? edge.targetNodeId}</td>
          <td><StatusPill value={edge.evidence} /></td>
          <td>{formatDateTime(edge.observedAt)}</td>
          <td><EvidenceLinks compact edge={edge} investigation={investigation} /></td>
        </tr>;
      })}
    </tbody></DataTable>
  </Panel>;
}

function NodeLinks({ node }: { node: InvestigationNodeDto }) {
  const { t } = useI18n();
  const links = [];
  if (node.incidentId !== null) links.push(<Link key="incident" to={`/incidents/${node.incidentId}`}>Incident {node.incidentId}</Link>);
  if (node.alertId !== null) links.push(<Link key="alert" to={`/alerts/${node.alertId}`}>Alert {node.alertId}</Link>);
  if (node.eventId && node.endpointId !== null && node.occurredAt) links.push(<Link key="event" to={`/events/${node.eventId}?endpointId=${node.endpointId}&occurredAt=${encodeURIComponent(node.occurredAt)}`}>Event {node.eventId}</Link>);
  if (node.endpointId !== null) links.push(<Link key="endpoint" to={`/endpoints/${node.endpointId}`}>Endpoint {node.endpointId}</Link>);
  return links.length ? <div className="context-links"><span>{t("incident.sourceRecord")}</span>{links}</div> : null;
}

function EvidenceLinks({ edge, investigation, compact = false }: { edge: InvestigationEdgeDto; investigation: IncidentInvestigationDto; compact?: boolean }) {
  const eventNode = investigation.nodes.find((node) => node.eventId && node.eventId === edge.eventId);
  const links = [];
  if (edge.eventId && eventNode?.endpointId !== null && eventNode?.occurredAt) links.push(<Link key="event" to={`/events/${edge.eventId}?endpointId=${eventNode.endpointId}&occurredAt=${encodeURIComponent(eventNode.occurredAt)}`}>Event</Link>);
  if (edge.alertId !== null) links.push(<Link key="alert" to={`/alerts/${edge.alertId}`}>Alert</Link>);
  if (edge.incidentId !== null) links.push(<Link key="incident" to={`/incidents/${edge.incidentId}`}>Incident</Link>);
  if (!links.length) return <span>—</span>;
  return <div className={compact ? "evidence-links compact" : "evidence-links"}>{links}</div>;
}

function nodeDefinitionItems(node: InvestigationNodeDto, t: ReturnType<typeof useI18n>["t"]) {
  return [
    { label: t("incident.nodeType"), value: node.nodeType },
    { label: "Endpoint", value: node.endpointId ?? t("common.notAvailable") },
    { label: "PID", value: node.pid ?? t("common.notAvailable") },
    { label: t("incident.process"), value: displayNullable(node.processName) },
    { label: t("incident.destination"), value: displayNullable(node.destination) },
    { label: t("incident.protocol"), value: displayNullable(node.protocol) },
    { label: t("incident.observedAt"), value: formatDateTime(node.occurredAt) },
    { label: "Risk", value: node.riskScore ?? t("common.notAvailable") },
  ];
}
