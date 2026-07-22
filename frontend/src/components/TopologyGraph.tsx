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
import type { EgressTopologyDto } from "../contracts";
import {
  endpointNodeId,
  groupTopologyEdges,
  targetNodeId,
  type TopologyDomainGroup,
  type TopologyEdgeGroup,
  type TopologySelection,
} from "../features/intelligenceOperations";
import "@xyflow/react/dist/style.css";

const NODE_WIDTH = 160;
const NODE_HEIGHT = 64;
const EDGE_LABEL_GAP = 40;
const EDGE_LABEL_LANE_OFFSET = 50;
const EDGE_LABEL_TARGET_HEIGHT = 36;
const FIT_VIEW_PADDING = 0.1;
const GRAPH_VERTICAL_MARGIN = 64;

interface TopologyGraphNodeData extends Record<string, unknown> {
  label: ReactNode;
}

interface TopologyGraphEdgeData extends Record<string, unknown> {
  alertCount: number;
  ariaLabel: string;
  labelXOffset: number;
  labelY: number;
  onSelect: (restoreFocus: boolean) => void;
}

type TopologyGraphEdge = Edge<TopologyGraphEdgeData, "topology">;

const topologyEdgeTypes = { topology: TopologyEdge };

function TopologyEdge({
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
}: EdgeProps<TopologyGraphEdge>) {
  const [path, labelXCenter, defaultLabelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const labelX = labelXCenter + (data?.labelXOffset ?? 0);
  const labelY = data?.labelY ?? defaultLabelY;
  const visualState = topologyEdgeVisualState(data?.alertCount ?? 0);
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
        className={`topology-edge-label ${visualState}${selected ? " selected" : ""} nodrag nopan`}
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

export function TopologyGraph({
  topology,
  selection,
  onSelect,
  label,
  destinationLabel,
  domainGroupLabel,
  domainGroups,
  hostsLabel,
}: {
  topology: EgressTopologyDto;
  selection: TopologySelection | null;
  onSelect: (selection: TopologySelection) => void;
  label: string;
  destinationLabel: string;
  domainGroupLabel: string;
  domainGroups: readonly TopologyDomainGroup[];
  hostsLabel: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const flowRef = useRef<ReactFlowInstance<Node<TopologyGraphNodeData>, TopologyGraphEdge> | null>(null);
  const fitFrameRef = useRef<number | null>(null);
  const focusFrameRef = useRef<number | null>(null);
  const scheduleEdgeFocus = useCallback((edgeId: string) => {
    if (typeof window === "undefined") return;
    if (focusFrameRef.current !== null) window.cancelAnimationFrame(focusFrameRef.current);
    focusFrameRef.current = window.requestAnimationFrame(() => {
      focusFrameRef.current = window.requestAnimationFrame(() => {
        focusFrameRef.current = null;
        const nextTarget = [...(containerRef.current?.querySelectorAll<HTMLButtonElement>(".topology-edge-label") ?? [])]
          .find((element) => element.dataset.edgeId === edgeId);
        nextTarget?.focus({ preventScroll: true });
      });
    });
  }, []);
  const edgeGroups = groupTopologyEdges(topology);
  const positions = layoutTopologyNodes(topology);
  const edgeLabelPositions = layoutTopologyEdgeLabels(edgeGroups, positions);
  const graphMinHeight = topologyGraphMinHeight(positions, edgeLabelPositions);
  const domainGroupByDomain = new Map(domainGroups.map((group) => [group.domain, group]));
  const nodeIds = new Set<string>();
  for (const node of topology.nodes) nodeIds.add(endpointNodeId(node.endpointId));
  for (const edge of edgeGroups) nodeIds.add(targetNodeId(edge.target));
  const nodes: Node<TopologyGraphNodeData>[] = [...nodeIds].map((id) => {
    const endpoint = id.startsWith("endpoint:") ? topology.nodes.find((item) => endpointNodeId(item.endpointId) === id) : null;
    const target = endpoint ? null : id.slice(7);
    const domainGroup = target ? domainGroupByDomain.get(target) : null;
    const nodeType = endpoint
      ? "ENDPOINT"
      : domainGroup ? `${domainGroupLabel.toUpperCase()} · ${domainGroup.targets.length} ${hostsLabel.toUpperCase()}` : destinationLabel.toUpperCase();
    const nodeLabel = endpoint ? `${endpoint.hostname} · Risk ${endpoint.riskScore}` : target ?? "";
    return {
      id,
      position: positions.get(id) ?? { x: 0, y: 0 },
      data: {
        label: <span className="topology-node-label"><small>{nodeType}</small><strong>{nodeLabel}</strong></span>,
      },
      ariaLabel: endpoint
        ? `Endpoint ${endpoint.hostname}, risk ${endpoint.riskScore}`
        : `${domainGroup ? domainGroupLabel : destinationLabel} ${target}`,
      className: endpoint ? "topology-flow-node endpoint" : `topology-flow-node target${domainGroup ? " domain-group" : ""}`,
      draggable: false,
      focusable: true,
      selectable: true,
      selected: selection?.kind === "NODE" && selection.id === id,
    };
  });
  const edges: TopologyGraphEdge[] = edgeGroups.map((edge) => {
    const protocolLabel = edge.protocols.length === 1 ? edge.protocols[0] : `${edge.protocols[0]} +${edge.protocols.length - 1}`;
    return {
      id: edge.id,
      source: endpointNodeId(edge.endpointId),
      target: targetNodeId(edge.target),
      label: `${protocolLabel} · E${edge.eventCount} A${edge.alertCount}`,
      ariaRole: "presentation",
      markerEnd: { type: MarkerType.ArrowClosed },
      focusable: false,
      selected: selection?.kind === "EDGE_GROUP" && selection.id === edge.id,
      className: `topology-edge ${topologyEdgeVisualState(edge.alertCount)}`,
      animated: false,
      data: {
        alertCount: edge.alertCount,
        ariaLabel: `${edge.protocols.join(", ")}, ${edge.eventCount} Events, ${edge.alertCount} Alerts`,
        labelXOffset: edgeLabelPositions.get(edge.id)?.xOffset ?? 0,
        labelY: edgeLabelPositions.get(edge.id)?.y ?? 0,
        onSelect: (restoreFocus) => {
          onSelect({ kind: "EDGE_GROUP", id: edge.id });
          if (restoreFocus) scheduleEdgeFocus(edge.id);
        },
      },
      type: "topology",
    };
  });
  const layoutSignature = `${[...nodeIds].sort().join("|")}::${edgeGroups.map((edge) => edge.id).sort().join("|")}`;
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

  return <div className="topology-flow" ref={containerRef} style={{ minHeight: graphMinHeight }}><ReactFlow
    aria-label={label}
    edgeTypes={topologyEdgeTypes}
    edges={edges}
    fitView
    fitViewOptions={{ maxZoom: 1, padding: FIT_VIEW_PADDING }}
    maxZoom={1.5}
    minZoom={0.65}
    nodes={nodes}
    nodesConnectable={false}
    nodesDraggable={false}
    onEdgeClick={(_, edge) => onSelect({ kind: "EDGE_GROUP", id: edge.id })}
    onInit={(instance) => {
      flowRef.current = instance;
      scheduleFitView(instance);
    }}
    onKeyDownCapture={(event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const nextSelection = topologySelectionFromElement(event.target instanceof Element ? event.target : null);
      if (!nextSelection || nextSelection.kind !== "NODE") return;
      event.preventDefault();
      event.stopPropagation();
      onSelect(nextSelection);
      window.requestAnimationFrame(() => {
        const nextTarget = [...(containerRef.current?.querySelectorAll<HTMLElement>(".react-flow__node, .react-flow__edge") ?? [])]
          .find((element) => element.dataset.id === nextSelection.id);
        nextTarget?.focus({ preventScroll: true });
      });
    }}
    onNodeClick={(_, node) => onSelect({ kind: "NODE", id: node.id })}
    proOptions={{ hideAttribution: true }}
  ><Controls showInteractive={false} /><Background color="var(--color-line)" gap={20} size={1} variant={BackgroundVariant.Dots} /></ReactFlow></div>;
}

export function topologyEdgeVisualState(alertCount: number): "has-alerts" | "observed-only" {
  return alertCount > 0 ? "has-alerts" : "observed-only";
}

export function topologySelectionFromElement(element: Element | null): TopologySelection | null {
  const graphElement = element?.closest<HTMLElement>(".react-flow__node, .react-flow__edge");
  const id = graphElement?.dataset.id;
  if (!id) return null;
  return graphElement.classList.contains("react-flow__node")
    ? { kind: "NODE", id }
    : { kind: "EDGE_GROUP", id };
}

export function topologyGraphMinHeight(
  positions: ReadonlyMap<string, { x: number; y: number }>,
  labelPositions: ReadonlyMap<string, { xOffset: number; y: number }> = new Map(),
): number {
  if (positions.size === 0) return 420;
  const yValues = [...positions.values()].map(({ y }) => y);
  const nodeTop = Math.min(...yValues);
  const nodeBottom = Math.max(...yValues) + NODE_HEIGHT;
  const nodeCenter = (nodeTop + nodeBottom) / 2;
  const labelCenters = [...labelPositions.values()].map(({ y }) => y);
  const visualTop = labelCenters.length
    ? Math.min(nodeTop, Math.min(...labelCenters) - EDGE_LABEL_TARGET_HEIGHT / 2)
    : nodeTop;
  const visualBottom = labelCenters.length
    ? Math.max(nodeBottom, Math.max(...labelCenters) + EDGE_LABEL_TARGET_HEIGHT / 2)
    : nodeBottom;
  const centeredContentHeight = Math.max(nodeCenter - visualTop, visualBottom - nodeCenter) * 2;
  return Math.max(420, Math.ceil(centeredContentHeight * (1 + FIT_VIEW_PADDING * 2) + GRAPH_VERTICAL_MARGIN));
}

export function layoutTopologyNodes(
  topology: Pick<EgressTopologyDto, "nodes" | "edges">,
): ReadonlyMap<string, { x: number; y: number }> {
  const edgeGroups = groupTopologyEdges(topology);
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "LR",
    nodesep: 24,
    ranksep: 210,
    edgesep: 32,
    marginx: 24,
    marginy: 24,
  });
  for (const node of topology.nodes) graph.setNode(endpointNodeId(node.endpointId), { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const edge of edgeGroups) {
    graph.setNode(targetNodeId(edge.target), { width: NODE_WIDTH, height: NODE_HEIGHT });
    graph.setEdge(endpointNodeId(edge.endpointId), targetNodeId(edge.target));
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

export function layoutTopologyEdgeLabels(
  edgeGroups: readonly TopologyEdgeGroup[],
  positions: ReadonlyMap<string, { x: number; y: number }>,
): ReadonlyMap<string, { xOffset: number; y: number }> {
  const candidates = edgeGroups.map((edge) => {
    const source = positions.get(endpointNodeId(edge.endpointId)) ?? { x: 0, y: 0 };
    const target = positions.get(targetNodeId(edge.target)) ?? { x: 0, y: 0 };
    const [, , labelY] = getBezierPath({
      sourceX: source.x + NODE_WIDTH / 2,
      sourceY: source.y + NODE_HEIGHT,
      sourcePosition: Position.Bottom,
      targetX: target.x + NODE_WIDTH / 2,
      targetY: target.y,
      targetPosition: Position.Top,
    });
    return { id: edge.id, labelY };
  }).sort((left, right) => left.labelY - right.labelY || left.id.localeCompare(right.id));

  if (candidates.length === 1) {
    const { id, labelY } = candidates[0]!;
    return new Map([[id, { xOffset: 0, y: labelY }]]);
  }

  const previousLabelY = [Number.NEGATIVE_INFINITY, Number.NEGATIVE_INFINITY];
  return new Map(candidates.map(({ id, labelY }) => {
    const adjustedYByLane = previousLabelY.map((previousY) => Math.max(labelY, previousY + EDGE_LABEL_GAP));
    const lane = adjustedYByLane[0]! <= adjustedYByLane[1]! ? 0 : 1;
    const adjustedY = adjustedYByLane[lane]!;
    previousLabelY[lane] = adjustedY;
    return [id, {
      xOffset: lane === 0 ? -EDGE_LABEL_LANE_OFFSET : EDGE_LABEL_LANE_OFFSET,
      y: adjustedY,
    }];
  }));
}
