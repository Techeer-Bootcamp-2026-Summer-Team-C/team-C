import dagre from "@dagrejs/dagre";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import type { ReactNode } from "react";
import type { IncidentInvestigationDto, InvestigationNodeDto } from "../contracts";
import type { InvestigationSelection } from "../features/incidentInvestigation";
import "@xyflow/react/dist/style.css";

const NODE_WIDTH = 160;
const NODE_HEIGHT = 64;

interface GraphNodeData extends Record<string, unknown> {
  label: ReactNode;
  source: InvestigationNodeDto;
}

export function IncidentGraph({
  investigation,
  selection,
  onSelect,
}: {
  investigation: IncidentInvestigationDto;
  selection: InvestigationSelection | null;
  onSelect: (selection: InvestigationSelection) => void;
}) {
  const positions = layoutInvestigationNodes(investigation);
  const nodes: Node<GraphNodeData>[] = investigation.nodes.map((node) => ({
    id: node.nodeId,
    position: positions.get(node.nodeId) ?? { x: 0, y: 0 },
    data: {
      source: node,
      label: <span className="investigation-node-label"><small>{node.nodeType}</small><strong>{node.label}</strong></span>,
    },
    ariaLabel: `${node.nodeType}: ${node.label}`,
    className: `investigation-node node-${node.nodeType.toLowerCase()}`,
    selected: selection?.kind === "NODE" && selection.id === node.nodeId,
    draggable: false,
    selectable: true,
  }));
  const edges: Edge[] = investigation.edges.map((edge) => ({
    id: edge.edgeId,
    source: edge.sourceNodeId,
    target: edge.targetNodeId,
    label: edge.relation.replaceAll("_", " "),
    ariaLabel: `${edge.relation}, ${edge.evidence}`,
    markerEnd: { type: MarkerType.ArrowClosed },
    selected: selection?.kind === "EDGE" && selection.id === edge.edgeId,
    className: "investigation-edge",
    animated: false,
  }));

  return <div aria-label="Incident investigation graph" className="investigation-graph" role="application">
    <ReactFlow
      edges={edges}
      fitView
      maxZoom={1.5}
      minZoom={0.2}
      nodes={nodes}
      nodesConnectable={false}
      nodesDraggable={false}
      onEdgeClick={(_, edge) => onSelect({ kind: "EDGE", id: edge.id })}
      onNodeClick={(_, node) => onSelect({ kind: "NODE", id: node.id })}
      proOptions={{ hideAttribution: true }}
    >
      <Controls showInteractive={false} />
      <Background color="var(--color-line)" gap={20} size={1} variant={BackgroundVariant.Dots} />
    </ReactFlow>
  </div>;
}

export function layoutInvestigationNodes(
  investigation: Pick<IncidentInvestigationDto, "nodes" | "edges">,
): ReadonlyMap<string, { x: number; y: number }> {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "LR", nodesep: 28, ranksep: 56, marginx: 20, marginy: 20 });
  for (const node of investigation.nodes) graph.setNode(node.nodeId, { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const edge of investigation.edges) graph.setEdge(edge.sourceNodeId, edge.targetNodeId);
  dagre.layout(graph);
  return new Map(investigation.nodes.map((node) => {
    const position = graph.node(node.nodeId) as { x: number; y: number } | undefined;
    return [node.nodeId, {
      x: (position?.x ?? NODE_WIDTH / 2) - NODE_WIDTH / 2,
      y: (position?.y ?? NODE_HEIGHT / 2) - NODE_HEIGHT / 2,
    }];
  }));
}
