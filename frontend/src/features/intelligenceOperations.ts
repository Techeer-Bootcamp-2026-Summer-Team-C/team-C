import type {
  ArchiveBucketDto,
  CorrelationDto,
  CorrelationRelationshipDto,
  EgressTopologyDto,
  IngestSummaryDto,
  OperationsHealthDto,
  SensorHealth,
  StorageStatus,
  TopologyEdgeDto,
} from "../contracts";

export type TopologySelection =
  | { kind: "NODE"; id: string }
  | { kind: "EDGE"; id: string }
  | { kind: "EDGE_GROUP"; id: string };

export interface TopologyEdgeGroup {
  id: string;
  endpointId: number;
  sourceLabel: string;
  target: string;
  protocols: string[];
  eventCount: number;
  alertCount: number;
  lastSeenAt: string;
  edges: TopologyEdgeDto[];
}

export type CorrelationSelection =
  | { kind: "NODE"; id: string }
  | { kind: "EDGE"; id: string };

export type PipelineStageId = "COLLECTION" | "DETECTION" | "STORAGE";

export interface PipelineSnapshotStage {
  id: PipelineStageId;
  status: SensorHealth;
}

const STORAGE_LIFECYCLE: readonly StorageStatus[] = [
  "HOT",
  "ARCHIVED",
  "RESTORE_REQUESTED",
  "RESTORED",
  "RESTORE_FAILED",
  "EXPIRED",
];

const HEALTH_PRIORITY: Record<SensorHealth, number> = {
  UNAVAILABLE: 0,
  DEGRADED: 1,
  HEALTHY: 2,
};

export function topologyGraphEnabled(value = import.meta.env.VITE_TOPOLOGY_GRAPH_ENABLED): boolean {
  return value !== "false" && value !== "0";
}

export function topologyEdgeId(endpointId: number, target: string, protocol: string): string {
  return `${endpointId}|${target}|${protocol}`;
}

export function topologyEdgeGroupId(endpointId: number, target: string): string {
  return `topology-group:${endpointId}:${encodeURIComponent(target)}`;
}

export function groupTopologyEdges(topology: Pick<EgressTopologyDto, "edges">): TopologyEdgeGroup[] {
  const groups = new Map<string, TopologyEdgeGroup>();
  for (const edge of topology.edges) {
    const id = topologyEdgeGroupId(edge.endpointId, edge.target);
    const current = groups.get(id);
    if (!current) {
      groups.set(id, {
        id,
        endpointId: edge.endpointId,
        sourceLabel: edge.sourceLabel,
        target: edge.target,
        protocols: [edge.protocol],
        eventCount: edge.eventCount,
        alertCount: edge.alertCount,
        lastSeenAt: edge.lastSeenAt,
        edges: [edge],
      });
      continue;
    }
    current.edges.push(edge);
    if (!current.protocols.includes(edge.protocol)) current.protocols.push(edge.protocol);
    current.eventCount += edge.eventCount;
    current.alertCount += edge.alertCount;
    if (Date.parse(edge.lastSeenAt) > Date.parse(current.lastSeenAt)) current.lastSeenAt = edge.lastSeenAt;
  }
  return [...groups.values()].map((group) => ({ ...group, protocols: group.protocols.slice().sort() }));
}

export function endpointNodeId(endpointId: number): string {
  return `endpoint:${endpointId}`;
}

export function targetNodeId(target: string): string {
  return `target:${target}`;
}

export function correlationNodeId(valueType: "IP" | "DOMAIN", value: string): string {
  return `correlation:${valueType}:${value}`;
}

export function correlationEdgeId(edge: CorrelationRelationshipDto): string {
  return `correlation-edge:${edge.relation}:${edge.sourceType}:${edge.sourceValue}:${edge.targetType}:${edge.targetValue}`;
}

export function selectedCorrelationRelationship(
  correlation: CorrelationDto,
  selection: CorrelationSelection | null,
): CorrelationRelationshipDto | null {
  if (selection?.kind !== "EDGE") return null;
  return correlation.relationships.find((edge) => correlationEdgeId(edge) === selection.id) ?? null;
}

export function filterTopology(topology: EgressTopologyDto, search: string, limit: number): EgressTopologyDto {
  const normalized = search.trim().toLocaleLowerCase();
  const nodeByEndpoint = new Map(topology.nodes.map((node) => [node.endpointId, node]));
  const matching = topology.edges.filter((edge) => {
    if (!normalized) return true;
    const endpoint = nodeByEndpoint.get(edge.endpointId);
    return [edge.sourceLabel, endpoint?.hostname, String(edge.endpointId), edge.target, edge.protocol]
      .some((value) => value?.toLocaleLowerCase().includes(normalized));
  });
  const edges = matching.slice().sort(compareTopologyEdges).slice(0, Math.max(1, limit));
  const endpointIds = new Set(edges.map((edge) => edge.endpointId));
  const nodes = topology.nodes.filter((node) => endpointIds.has(node.endpointId));
  return { ...topology, nodes, edges };
}

export function selectedTopologyEdge(
  topology: EgressTopologyDto,
  selection: TopologySelection | null,
): TopologyEdgeDto | null {
  if (selection?.kind !== "EDGE") return null;
  return topology.edges.find((edge) => topologyEdgeId(edge.endpointId, edge.target, edge.protocol) === selection.id) ?? null;
}

export function selectedTopologyEdgeGroup(
  topology: EgressTopologyDto,
  selection: TopologySelection | null,
): TopologyEdgeGroup | null {
  if (selection?.kind !== "EDGE_GROUP") return null;
  return groupTopologyEdges(topology).find((group) => group.id === selection.id) ?? null;
}

export function buildPipelineSnapshot(
  health: OperationsHealthDto,
  ingest: IngestSummaryDto,
): PipelineSnapshotStage[] {
  const collection = worstHealth(health.services
    .filter((service) => ["Backend API", "Kafka"].includes(service.service))
    .map((service) => service.status));
  const workerStatuses: SensorHealth[] = health.workers.map((worker) => {
    if (worker.status === "OFFLINE") return "UNAVAILABLE";
    if (worker.status === "IDLE" || worker.status === "UNKNOWN" || (worker.lag ?? 0) > 0) return "DEGRADED";
    return "HEALTHY";
  });
  if (ingest.eventFailures.failedCount > 0 || ingest.eventFailures.reprocessFailedCount > 0) {
    workerStatuses.push("DEGRADED");
  }
  const detection = worstHealth(workerStatuses);
  const storageStatuses = health.services
    .filter((service) => ["PostgreSQL", "ClickHouse", "S3"].includes(service.service))
    .map((service) => service.status);
  if (ingest.storage.failedBucketCount > 0) storageStatuses.push("DEGRADED");
  const storage = worstHealth(storageStatuses);
  const stages: PipelineSnapshotStage[] = [
    { id: "COLLECTION", status: collection },
    { id: "DETECTION", status: detection },
    { id: "STORAGE", status: storage },
  ];
  return stages.sort((left, right) => HEALTH_PRIORITY[left.status] - HEALTH_PRIORITY[right.status]);
}

export function archiveLifecycleCounts(items: readonly ArchiveBucketDto[]): Array<{ status: StorageStatus; count: number }> {
  return STORAGE_LIFECYCLE.map((status) => ({
    status,
    count: items.filter((item) => item.storageStatus === status).length,
  }));
}

function worstHealth(statuses: readonly SensorHealth[]): SensorHealth {
  if (!statuses.length) return "UNAVAILABLE";
  return statuses.reduce((worst, status) => HEALTH_PRIORITY[status] < HEALTH_PRIORITY[worst] ? status : worst, "HEALTHY");
}

function compareTopologyEdges(left: TopologyEdgeDto, right: TopologyEdgeDto): number {
  return right.alertCount - left.alertCount
    || right.eventCount - left.eventCount
    || Date.parse(right.lastSeenAt) - Date.parse(left.lastSeenAt)
    || left.endpointId - right.endpointId
    || left.target.localeCompare(right.target)
    || left.protocol.localeCompare(right.protocol);
}
