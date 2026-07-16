import dagre from "@dagrejs/dagre";
import { Background, BackgroundVariant, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import type { CorrelationDto } from "../contracts";
import {
  correlationEdgeId,
  correlationNodeId,
  type CorrelationSelection,
} from "../features/intelligenceOperations";
import "@xyflow/react/dist/style.css";

export function CorrelationGraph({
  correlation,
  selection,
  onSelect,
  label,
}: {
  correlation: CorrelationDto;
  selection: CorrelationSelection | null;
  onSelect: (selection: CorrelationSelection) => void;
  label: string;
}) {
  const values = new Map<string, { value: string; valueType: "IP" | "DOMAIN"; input: boolean }>();
  const addValue = (valueType: "IP" | "DOMAIN", value: string, input = false) => {
    const id = correlationNodeId(valueType, value);
    const existing = values.get(id);
    values.set(id, { value, valueType, input: input || existing?.input === true });
  };

  addValue(correlation.inputType, correlation.inputValue, true);
  for (const value of correlation.related) addValue(value.valueType, value.value);
  for (const edge of correlation.relationships) {
    addValue(edge.sourceType, edge.sourceValue);
    addValue(edge.targetType, edge.targetValue);
  }

  const graph = new dagre.graphlib.Graph()
    .setDefaultEdgeLabel(() => ({}))
    .setGraph({ rankdir: "LR", ranksep: 100, nodesep: 36 });
  for (const id of values.keys()) graph.setNode(id, { width: 190, height: 68 });
  for (const edge of correlation.relationships) {
    graph.setEdge(
      correlationNodeId(edge.sourceType, edge.sourceValue),
      correlationNodeId(edge.targetType, edge.targetValue),
    );
  }
  dagre.layout(graph);

  const nodes: Node[] = [...values.entries()].map(([id, item]) => {
    const point = graph.node(id);
    return {
      id,
      position: { x: point.x - 95, y: point.y - 34 },
      data: { label: `${item.valueType} · ${item.value}` },
      ariaLabel: `${item.input ? "Input " : ""}${item.valueType} ${item.value}`,
      className: `topology-flow-node correlation ${item.valueType.toLowerCase()}${item.input ? " input" : ""}`,
      draggable: false,
      focusable: true,
      selectable: true,
      selected: selection?.kind === "NODE" && selection.id === id,
    };
  });
  const edges: Edge[] = correlation.relationships.map((edge) => {
    const id = correlationEdgeId(edge);
    const evidence = edge.sources.map((source) => source === "LIVE_DNS" ? "LIVE" : "OBSERVED").join(" + ");
    return {
      id,
      source: correlationNodeId(edge.sourceType, edge.sourceValue),
      target: correlationNodeId(edge.targetType, edge.targetValue),
      label: `${edge.relation.replaceAll("_", " ")} · ${evidence}`,
      ariaLabel: `${edge.sourceValue} ${edge.relation} ${edge.targetValue}, ${evidence}`,
      markerEnd: { type: MarkerType.ArrowClosed },
      focusable: true,
      selected: selection?.kind === "EDGE" && selection.id === id,
      animated: false,
    };
  });

  return <div aria-label={label} className="topology-flow correlation-flow" role="application"><ReactFlow edges={edges} fitView maxZoom={1.5} minZoom={0.25} nodes={nodes} nodesConnectable={false} nodesDraggable={false} onEdgeClick={(_, edge) => onSelect({ kind: "EDGE", id: edge.id })} onNodeClick={(_, node) => onSelect({ kind: "NODE", id: node.id })} proOptions={{ hideAttribution: true }}><Controls showInteractive={false} /><Background color="var(--color-line)" gap={20} size={1} variant={BackgroundVariant.Dots} /></ReactFlow></div>;
}
