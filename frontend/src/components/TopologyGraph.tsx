import dagre from "@dagrejs/dagre";
import { Background, BackgroundVariant, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import type { EgressTopologyDto } from "../contracts";
import {
  endpointNodeId,
  targetNodeId,
  topologyEdgeId,
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
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({})).setGraph({ rankdir: "LR", ranksep: 100, nodesep: 36 });
  const nodeIds = new Set<string>();
  for (const node of topology.nodes) { const id = endpointNodeId(node.endpointId); nodeIds.add(id); graph.setNode(id, { width: 180, height: 64 }); }
  for (const edge of topology.edges) { const id = targetNodeId(edge.target); if (!nodeIds.has(id)) { nodeIds.add(id); graph.setNode(id, { width: 180, height: 64 }); } graph.setEdge(endpointNodeId(edge.endpointId), id); }
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
      selectable: true,
      selected: selection?.kind === "NODE" && selection.id === id,
    };
  });
  const edges: Edge[] = topology.edges.map((edge) => {
    const id = topologyEdgeId(edge.endpointId, edge.target, edge.protocol);
    return {
      id,
      source: endpointNodeId(edge.endpointId),
      target: targetNodeId(edge.target),
      label: `${edge.protocol} · E${edge.eventCount} A${edge.alertCount}`,
      ariaLabel: `${edge.protocol}, ${edge.eventCount} Events, ${edge.alertCount} Alerts`,
      markerEnd: { type: MarkerType.ArrowClosed },
      focusable: true,
      selected: selection?.kind === "EDGE" && selection.id === id,
      animated: false,
    };
  });
  return <div aria-label={label} className="topology-flow" role="application"><ReactFlow edges={edges} fitView maxZoom={1.5} minZoom={0.25} nodes={nodes} nodesConnectable={false} nodesDraggable={false} onEdgeClick={(_, edge) => onSelect({ kind: "EDGE", id: edge.id })} onNodeClick={(_, node) => onSelect({ kind: "NODE", id: node.id })} proOptions={{ hideAttribution: true }}><Controls showInteractive={false} /><Background color="var(--color-line)" gap={20} size={1} variant={BackgroundVariant.Dots} /></ReactFlow></div>;
}
