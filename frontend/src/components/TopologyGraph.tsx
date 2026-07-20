import dagre from "@dagrejs/dagre";
import { Background, BackgroundVariant, Controls, MarkerType, Position, ReactFlow, type Edge, type Node } from "@xyflow/react";
import type { EgressTopologyDto } from "../contracts";
import {
  endpointNodeId,
  groupTopologyEdges,
  targetNodeId,
  type TopologySelection,
} from "../features/intelligenceOperations";
import "@xyflow/react/dist/style.css";

export function TopologyGraph({
  topology,
  selection,
  onSelect,
  label,
}: {
  topology: EgressTopologyDto;
  selection: TopologySelection | null;
  onSelect: (selection: TopologySelection) => void;
  label: string;
}) {
  const edgeGroups = groupTopologyEdges(topology);
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({})).setGraph({ rankdir: "LR", ranksep: 100, nodesep: 36 });
  const nodeIds = new Set<string>();
  for (const node of topology.nodes) { const id = endpointNodeId(node.endpointId); nodeIds.add(id); graph.setNode(id, { width: 180, height: 64 }); }
  for (const edge of edgeGroups) { const id = targetNodeId(edge.target); if (!nodeIds.has(id)) { nodeIds.add(id); graph.setNode(id, { width: 180, height: 64 }); } graph.setEdge(endpointNodeId(edge.endpointId), id); }
  dagre.layout(graph);
  const nodes: Node[] = [...nodeIds].map((id) => {
    const point = graph.node(id);
    const endpoint = id.startsWith("endpoint:") ? topology.nodes.find((item) => endpointNodeId(item.endpointId) === id) : null;
    return {
      id,
      position: { x: point.x - 90, y: point.y - 32 },
      data: { label: endpoint ? `${endpoint.hostname} · Risk ${endpoint.riskScore}` : id.slice(7) },
      ariaLabel: endpoint ? `Endpoint ${endpoint.hostname}, risk ${endpoint.riskScore}` : `Target ${id.slice(7)}`,
      className: endpoint ? "topology-flow-node endpoint" : "topology-flow-node target",
      draggable: false,
      focusable: true,
      ...(endpoint ? { sourcePosition: Position.Right } : { targetPosition: Position.Left }),
      selectable: true,
      selected: selection?.kind === "NODE" && selection.id === id,
    };
  });
  const edges: Edge[] = edgeGroups.map((edge) => {
    const protocolLabel = edge.protocols.length === 1 ? edge.protocols[0] : `${edge.protocols[0]} +${edge.protocols.length - 1}`;
    return {
      id: edge.id,
      source: endpointNodeId(edge.endpointId),
      target: targetNodeId(edge.target),
      label: `${protocolLabel} · E${edge.eventCount} A${edge.alertCount}`,
      ariaLabel: `${edge.protocols.join(", ")}, ${edge.eventCount} Events, ${edge.alertCount} Alerts`,
      markerEnd: { type: MarkerType.ArrowClosed },
      focusable: true,
      selected: selection?.kind === "EDGE_GROUP" && selection.id === edge.id,
      animated: false,
      type: "smoothstep",
    };
  });
  return <div aria-label={label} className="topology-flow" role="application"><ReactFlow edges={edges} fitView maxZoom={1.5} minZoom={0.25} nodes={nodes} nodesConnectable={false} nodesDraggable={false} onEdgeClick={(_, edge) => onSelect({ kind: "EDGE_GROUP", id: edge.id })} onNodeClick={(_, node) => onSelect({ kind: "NODE", id: node.id })} proOptions={{ hideAttribution: true }}><Controls showInteractive={false} /><Background color="var(--color-line)" gap={20} size={1} variant={BackgroundVariant.Dots} /></ReactFlow></div>;
}
