import type {
  AttackTimelineItemDto,
  IncidentInvestigationDto,
  IncidentListQuery,
  InvestigationEdgeDto,
  InvestigationNodeDto,
} from "../contracts";
import { readTimeFilter } from "../components/filters";
import { allowedValue, positiveInteger } from "../lib/params";

const INCIDENT_STATUSES = ["OPEN", "CLOSED"] as const;
const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
const SORT_ORDERS = ["asc", "desc"] as const;

export type InvestigationSelection =
  | { kind: "NODE"; id: string }
  | { kind: "EDGE"; id: string };

export function incidentGraphEnabled(value = import.meta.env.VITE_INCIDENT_GRAPH_ENABLED): boolean {
  return value !== "false" && value !== "0";
}

export function incidentDetailUrl(incidentId: number, params: URLSearchParams): string {
  const next = new URLSearchParams(params);
  next.set("selected", String(incidentId));
  const search = next.toString();
  return `/incidents/${incidentId}${search ? `?${search}` : ""}`;
}

export function incidentQueueQuery(params: URLSearchParams): IncidentListQuery {
  const time = readTimeFilter(params);
  const query: IncidentListQuery = {
    ...time.query,
    page: 1,
    size: 500,
    sortOrder: allowedValue(params.get("sortOrder"), SORT_ORDERS) ?? "desc",
    status: allowedValue(params.get("status"), INCIDENT_STATUSES) ?? "OPEN",
  };
  const severity = allowedValue(params.get("severity"), SEVERITIES);
  const endpointId = positiveInteger(params.get("endpointId"));
  if (severity) query.severity = severity;
  if (endpointId) query.endpointId = endpointId;
  return query;
}

export function graphRequiresFallback(investigation: IncidentInvestigationDto): boolean {
  return investigation.partial || investigation.truncated || investigation.nodes.length === 0;
}

export function selectedNode(
  selection: InvestigationSelection | null,
  investigation: IncidentInvestigationDto,
): InvestigationNodeDto | null {
  return selection?.kind === "NODE"
    ? investigation.nodes.find((node) => node.nodeId === selection.id) ?? null
    : null;
}

export function selectedEdge(
  selection: InvestigationSelection | null,
  investigation: IncidentInvestigationDto,
): InvestigationEdgeDto | null {
  return selection?.kind === "EDGE"
    ? investigation.edges.find((edge) => edge.edgeId === selection.id) ?? null
    : null;
}

export function selectionNodeIds(
  selection: InvestigationSelection | null,
  investigation: IncidentInvestigationDto,
): ReadonlySet<string> {
  if (!selection) return new Set();
  if (selection.kind === "NODE") return new Set([selection.id]);
  const edge = selectedEdge(selection, investigation);
  return edge ? new Set([edge.sourceNodeId, edge.targetNodeId]) : new Set();
}

export function selectionMatchesTimelineItem(
  selection: InvestigationSelection | null,
  investigation: IncidentInvestigationDto,
  item: AttackTimelineItemDto,
): boolean {
  if (!selection) return false;
  const nodes = investigation.nodes.filter((node) => selectionNodeIds(selection, investigation).has(node.nodeId));
  const edge = selectedEdge(selection, investigation);
  return nodes.some((node) => nodeMatchesTimeline(node, item))
    || Boolean(edge && edgeMatchesTimeline(edge, item));
}

export function selectionForTimelineItem(
  investigation: IncidentInvestigationDto,
  item: AttackTimelineItemDto,
): InvestigationSelection | null {
  const node = investigation.nodes.find((candidate) => nodeMatchesTimeline(candidate, item));
  return node ? { kind: "NODE", id: node.nodeId } : null;
}

export function selectedProcessPid(
  selection: InvestigationSelection | null,
  investigation: IncidentInvestigationDto | null,
): number | null {
  if (!investigation) return null;
  const direct = selectedNode(selection, investigation);
  if (direct?.nodeType === "PROCESS") return direct.pid;
  for (const nodeId of selectionNodeIds(selection, investigation)) {
    const node = investigation.nodes.find((candidate) => candidate.nodeId === nodeId);
    if (node?.nodeType === "PROCESS" && node.pid !== null) return node.pid;
  }
  return null;
}

function nodeMatchesTimeline(node: InvestigationNodeDto, item: AttackTimelineItemDto): boolean {
  if (node.nodeType !== item.itemType) return false;
  if (item.itemType === "EVENT") return Boolean(item.eventId && node.eventId === item.eventId);
  if (item.itemType === "ALERT") return Boolean(item.alertId && node.alertId === item.alertId);
  return Boolean(item.incidentId && node.incidentId === item.incidentId);
}

function edgeMatchesTimeline(edge: InvestigationEdgeDto, item: AttackTimelineItemDto): boolean {
  if (item.itemType === "EVENT") return Boolean(item.eventId && edge.eventId === item.eventId);
  if (item.itemType === "ALERT") return Boolean(item.alertId && edge.alertId === item.alertId);
  return Boolean(item.incidentId && edge.incidentId === item.incidentId);
}
