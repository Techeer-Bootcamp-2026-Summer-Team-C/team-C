import dagre from "@dagrejs/dagre";
import {
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  MarkerType,
  Position,
  ReactFlow,
  getBezierPath,
  type Edge,
  type EdgeProps,
  type Node,
  type ReactFlowInstance,
} from "@xyflow/react";
import { useCallback, useEffect, useRef, type ReactNode } from "react";
import type { CorrelationDto, CorrelationRelationshipDto } from "../contracts";
import {
  correlationEdgeId,
  correlationGraphRelationships,
  correlationNodeId,
  type CorrelationSelection,
} from "../features/intelligenceOperations";
import "@xyflow/react/dist/style.css";

const NODE_WIDTH = 160;
const NODE_HEIGHT = 64;
const EDGE_LABEL_GAP = 40;
const EDGE_LABEL_TARGET_HEIGHT = 36;
const FIT_VIEW_PADDING = 0.05;
const GRAPH_VERTICAL_MARGIN = 64;

interface CorrelationGraphNodeData extends Record<string, unknown> {
  label: ReactNode;
}

interface CorrelationGraphEdgeData extends Record<string, unknown> {
  ariaLabel: string;
  labelY: number;
  onSelect: (restoreFocus: boolean) => void;
  visualState: "live" | "observed-only";
}

type CorrelationGraphEdge = Edge<CorrelationGraphEdgeData, "correlation">;

const correlationEdgeTypes = { correlation: CorrelationEdge };

function CorrelationEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  label,
  data,
  style,
  markerEnd,
  markerStart,
  selected,
}: EdgeProps<CorrelationGraphEdge>) {
  const [path, labelX, defaultLabelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const labelY = data?.labelY ?? defaultLabelY;
  const visualState = data?.visualState ?? "observed-only";
  return <>
    <BaseEdge
      {...(markerEnd ? { markerEnd } : {})}
      {...(markerStart ? { markerStart } : {})}
      {...(style ? { style } : {})}
      id={id}
      path={path}
    />
    <EdgeLabelRenderer>
      <button
        aria-label={data?.ariaLabel ?? String(label ?? "")}
        aria-pressed={selected}
        className={`topology-edge-label correlation-edge-label ${visualState}${selected ? " selected" : ""} nodrag nopan`}
        data-edge-id={id}
        onClick={(event) => {
          event.stopPropagation();
          data?.onSelect(event.detail === 0);
        }}
        onMouseDown={(event) => event.stopPropagation()}
        style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
        type="button"
      >{label}</button>
    </EdgeLabelRenderer>
  </>;
}

export function CorrelationGraph({
  correlation,
  selection,
  onSelect,
  label,
  relationshipLimit,
  scopeLabel,
}: {
  correlation: CorrelationDto;
  selection: CorrelationSelection | null;
  onSelect: (selection: CorrelationSelection) => void;
  label: string;
  relationshipLimit?: number | undefined;
  scopeLabel?: string | undefined;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const flowRef = useRef<ReactFlowInstance<Node<CorrelationGraphNodeData>, CorrelationGraphEdge> | null>(null);
  const fitFrameRef = useRef<number | null>(null);
  const focusFrameRef = useRef<number | null>(null);
  const scheduleFocus = useCallback((selector: string, id: string, dataAttribute: "id" | "edgeId") => {
    if (typeof window === "undefined") return;
    if (focusFrameRef.current !== null) window.cancelAnimationFrame(focusFrameRef.current);
    focusFrameRef.current = window.requestAnimationFrame(() => {
      focusFrameRef.current = window.requestAnimationFrame(() => {
        focusFrameRef.current = null;
        const nextTarget = [...(containerRef.current?.querySelectorAll<HTMLElement>(selector) ?? [])]
          .find((element) => element.dataset[dataAttribute] === id);
        nextTarget?.focus({ preventScroll: true });
      });
    });
  }, []);

  const visibleRelationships = correlationGraphRelationships(correlation, relationshipLimit);
  const values = new Map<string, { value: string; valueType: "IP" | "DOMAIN"; input: boolean }>();
  const addValue = (valueType: "IP" | "DOMAIN", value: string, input = false) => {
    const id = correlationNodeId(valueType, value);
    const existing = values.get(id);
    values.set(id, { value, valueType, input: input || existing?.input === true });
  };
  addValue(correlation.inputType, correlation.inputValue, true);
  for (const edge of visibleRelationships) {
    addValue(edge.sourceType, edge.sourceValue);
    addValue(edge.targetType, edge.targetValue);
  }

  const positions = layoutCorrelationNodes(values.keys(), visibleRelationships);
  const edgeLabelYs = layoutCorrelationEdgeLabelYs(visibleRelationships, positions);
  const graphMinHeight = correlationGraphMinHeight(positions, edgeLabelYs);
  const nodes: Node<CorrelationGraphNodeData>[] = [...values.entries()].map(([id, item]) => ({
    id,
    position: positions.get(id) ?? { x: 0, y: 0 },
    data: {
      label: <span className="topology-node-label"><small>{item.input ? `INPUT · ${item.valueType}` : item.valueType}</small><strong>{item.value}</strong></span>,
    },
    ariaLabel: `${item.input ? "Input " : ""}${item.valueType} ${item.value}`,
    className: `topology-flow-node correlation ${item.valueType.toLowerCase()}${item.input ? " input" : ""}`,
    draggable: false,
    focusable: true,
    selectable: true,
    selected: selection?.kind === "NODE" && selection.id === id,
  }));
  const edges: CorrelationGraphEdge[] = visibleRelationships.map((edge) => {
    const id = correlationEdgeId(edge);
    const evidence = edge.sources.map((source) => source === "LIVE_DNS" ? "LIVE" : "OBS").join(" + ");
    const visualState = edge.sources.includes("LIVE_DNS") ? "live" : "observed-only";
    return {
      id,
      source: correlationNodeId(edge.sourceType, edge.sourceValue),
      target: correlationNodeId(edge.targetType, edge.targetValue),
      label: `${edge.relation.replaceAll("_", " ")} · ${evidence}`,
      ariaRole: "presentation",
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: visualState === "live" ? "var(--status-info)" : "var(--text-tertiary)",
      },
      focusable: false,
      selected: selection?.kind === "EDGE" && selection.id === id,
      animated: false,
      className: `correlation-edge ${visualState}`,
      data: {
        ariaLabel: `${edge.sourceValue} ${edge.relation} ${edge.targetValue}, ${evidence}`,
        labelY: edgeLabelYs.get(id) ?? 0,
        onSelect: (restoreFocus) => {
          onSelect({ kind: "EDGE", id });
          if (restoreFocus) scheduleFocus(".correlation-edge-label", id, "edgeId");
        },
        visualState,
      },
      type: "correlation",
    };
  });
  const layoutSignature = `${[...values.keys()].sort().join("|")}::${edges.map((edge) => edge.id).sort().join("|")}`;
  const scheduleFitView = useCallback((instance = flowRef.current) => {
    if (!instance || typeof window === "undefined") return;
    if (fitFrameRef.current !== null) window.cancelAnimationFrame(fitFrameRef.current);
    fitFrameRef.current = window.requestAnimationFrame(() => {
      fitFrameRef.current = null;
      void instance.fitView({ maxZoom: 1, padding: FIT_VIEW_PADDING });
    });
  }, []);

  useEffect(() => {
    scheduleFitView();
  }, [layoutSignature, scheduleFitView]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => scheduleFitView());
    observer.observe(container);
    return () => observer.disconnect();
  }, [scheduleFitView]);

  useEffect(() => () => {
    if (fitFrameRef.current !== null) window.cancelAnimationFrame(fitFrameRef.current);
    if (focusFrameRef.current !== null) window.cancelAnimationFrame(focusFrameRef.current);
  }, []);

  return <div className="correlation-graph-stack">
    {scopeLabel ? <p className="correlation-graph-scope">{scopeLabel}</p> : null}
    <div className="topology-flow correlation-flow" ref={containerRef} style={{ minHeight: graphMinHeight }}><ReactFlow
      aria-label={label}
      edgeTypes={correlationEdgeTypes}
      edges={edges}
      fitView
      fitViewOptions={{ maxZoom: 1, padding: FIT_VIEW_PADDING }}
      maxZoom={1.5}
      minZoom={0.4}
      nodes={nodes}
      nodesConnectable={false}
      nodesDraggable={false}
      onEdgeClick={(_, edge) => onSelect({ kind: "EDGE", id: edge.id })}
      onInit={(instance) => {
        flowRef.current = instance;
        scheduleFitView(instance);
      }}
      onKeyDownCapture={(event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const nextSelection = correlationSelectionFromElement(event.target instanceof Element ? event.target : null);
        if (!nextSelection || nextSelection.kind !== "NODE") return;
        event.preventDefault();
        event.stopPropagation();
        onSelect(nextSelection);
        scheduleFocus(".react-flow__node", nextSelection.id, "id");
      }}
      onNodeClick={(_, node) => onSelect({ kind: "NODE", id: node.id })}
      proOptions={{ hideAttribution: true }}
    ><Controls showInteractive={false} /><Background color="var(--color-line)" gap={20} size={1} variant={BackgroundVariant.Dots} /></ReactFlow></div>
  </div>;
}

export function correlationSelectionFromElement(element: Element | null): CorrelationSelection | null {
  const graphElement = element?.closest<HTMLElement>(".react-flow__node, .react-flow__edge");
  const id = graphElement?.dataset.id;
  if (!id) return null;
  return graphElement.classList.contains("react-flow__node")
    ? { kind: "NODE", id }
    : { kind: "EDGE", id };
}

export function correlationGraphMinHeight(
  positions: ReadonlyMap<string, { x: number; y: number }>,
  labelYs: ReadonlyMap<string, number> = new Map(),
): number {
  if (positions.size === 0) return 520;
  const yValues = [...positions.values()].map(({ y }) => y);
  const nodeTop = Math.min(...yValues);
  const nodeBottom = Math.max(...yValues) + NODE_HEIGHT;
  const nodeCenter = (nodeTop + nodeBottom) / 2;
  const labelCenters = [...labelYs.values()];
  const visualTop = labelCenters.length
    ? Math.min(nodeTop, Math.min(...labelCenters) - EDGE_LABEL_TARGET_HEIGHT / 2)
    : nodeTop;
  const visualBottom = labelCenters.length
    ? Math.max(nodeBottom, Math.max(...labelCenters) + EDGE_LABEL_TARGET_HEIGHT / 2)
    : nodeBottom;
  const centeredContentHeight = Math.max(nodeCenter - visualTop, visualBottom - nodeCenter) * 2;
  return Math.max(520, Math.ceil(centeredContentHeight * (1 + FIT_VIEW_PADDING * 2) + GRAPH_VERTICAL_MARGIN));
}

function layoutCorrelationNodes(
  nodeIds: Iterable<string>,
  relationships: readonly CorrelationRelationshipDto[],
): ReadonlyMap<string, { x: number; y: number }> {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "LR",
    ranksep: 180,
    nodesep: 24,
    edgesep: 32,
    marginx: 24,
    marginy: 24,
  });
  for (const id of nodeIds) graph.setNode(id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const edge of relationships) {
    graph.setEdge(
      correlationNodeId(edge.sourceType, edge.sourceValue),
      correlationNodeId(edge.targetType, edge.targetValue),
    );
  }
  dagre.layout(graph);
  return new Map(graph.nodes().map((id) => {
    const point = graph.node(id) as { x: number; y: number } | undefined;
    return [id, {
      x: (point?.x ?? NODE_WIDTH / 2) - NODE_WIDTH / 2,
      y: (point?.y ?? NODE_HEIGHT / 2) - NODE_HEIGHT / 2,
    }];
  }));
}

function layoutCorrelationEdgeLabelYs(
  relationships: readonly CorrelationRelationshipDto[],
  positions: ReadonlyMap<string, { x: number; y: number }>,
): ReadonlyMap<string, number> {
  const candidates = relationships.map((edge) => {
    const source = positions.get(correlationNodeId(edge.sourceType, edge.sourceValue)) ?? { x: 0, y: 0 };
    const target = positions.get(correlationNodeId(edge.targetType, edge.targetValue)) ?? { x: 0, y: 0 };
    const [, , labelY] = getBezierPath({
      sourceX: source.x + NODE_WIDTH / 2,
      sourceY: source.y + NODE_HEIGHT,
      sourcePosition: Position.Bottom,
      targetX: target.x + NODE_WIDTH / 2,
      targetY: target.y,
      targetPosition: Position.Top,
    });
    return { id: correlationEdgeId(edge), labelY };
  }).sort((left, right) => left.labelY - right.labelY || left.id.localeCompare(right.id));

  let previousLabelY = Number.NEGATIVE_INFINITY;
  return new Map(candidates.map(({ id, labelY }) => {
    const adjustedLabelY = Math.max(labelY, previousLabelY + EDGE_LABEL_GAP);
    previousLabelY = adjustedLabelY;
    return [id, adjustedLabelY];
  }));
}
