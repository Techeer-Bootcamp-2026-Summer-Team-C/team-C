import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../src/auth/AuthContext";
import {
  correlationGraphMinHeight,
  correlationSelectionFromElement,
} from "../src/components/CorrelationGraph";
import {
  layoutTopologyEdgeLabels,
  layoutTopologyNodes,
  topologyEdgeVisualState,
  topologyGraphMinHeight,
  topologySelectionFromElement,
} from "../src/components/TopologyGraph";
import type {
  ArchiveBucketDto,
  CorrelationDto,
  DashboardSummaryDto,
  EgressTopologyDto,
  IngestSummaryDto,
  OperationsHealthDto,
} from "../src/contracts";
import {
  CORRELATION_GRAPH_RELATIONSHIP_LIMIT,
  CORRELATION_INLINE_RELATIONSHIP_LIMIT,
  archiveLifecycleCounts,
  buildTopologyDomainView,
  buildPipelineSnapshot,
  correlationEdgeId,
  correlationGraphRelationships,
  filterTopology,
  groupTopologyEdges,
  registrableDomainForTarget,
  selectedCorrelationRelationship,
  selectedTopologyEdgeGroup,
  topologyEdgeGroupId,
  topologyGraphEnabled,
} from "../src/features/intelligenceOperations";
import { LocaleProvider } from "../src/i18n/LocaleContext";
import { ArchiveLifecycleBoard, ArchivesPage } from "../src/pages/ArchivesPage";
import { CorrelationResult, IntelligenceContent } from "../src/pages/IntelligencePage";
import { PipelineSnapshot } from "../src/pages/OperationsPage";
import { canMutate } from "../src/query/policy";

afterEach(() => { cleanup(); vi.restoreAllMocks(); sessionStorage.clear(); });

describe("WP-08 Intelligence, Operations, and Archives", () => {
  it("keeps topology filtering deterministic and the graph feature flag reversible", () => {
    const filtered = filterTopology(topologyFixture, "tcp", 1);
    expect(filtered.edges).toHaveLength(1);
    expect(filtered.edges[0]).toMatchObject({ endpointId: 1001, target: "203.0.113.10", alertCount: 2 });
    expect(filtered.nodes.map((node) => node.endpointId)).toEqual([1001]);
    expect(topologyGraphEnabled("false")).toBe(false);
    expect(topologyGraphEnabled("0")).toBe(false);
    expect(topologyGraphEnabled("true")).toBe(true);
    expect(filterTopology(topologyFixture, "missing-target", 10).edges).toEqual([]);
  });

  it("groups parallel protocol edges into one honest visual relationship", () => {
    const parallelTopology: EgressTopologyDto = {
      ...topologyFixture,
      edges: [
        topologyFixture.edges[0]!,
        { ...topologyFixture.edges[0]!, protocol: "TLS", eventCount: 3, alertCount: 1, lastSeenAt: "2026-07-15T04:00:00Z" },
      ],
    };
    const groups = groupTopologyEdges(parallelTopology);
    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({ endpointId: 1001, target: "203.0.113.10", protocols: ["TCP", "TLS"], eventCount: 8, alertCount: 3, lastSeenAt: "2026-07-15T04:00:00Z" });
    const selection = { kind: "EDGE_GROUP" as const, id: topologyEdgeGroupId(1001, "203.0.113.10") };
    expect(selectedTopologyEdgeGroup(parallelTopology, selection)).toEqual(groups[0]);
  });

  it("groups sibling subdomains by registrable domain without collapsing IP evidence", () => {
    const groupedInput: EgressTopologyDto = {
      ...topologyFixture,
      edges: [
        { ...topologyFixture.edges[1]!, endpointId: 1001, sourceLabel: "SOC-WIN-01", target: "api.corp.example", eventCount: 3, alertCount: 1 },
        { ...topologyFixture.edges[1]!, endpointId: 1001, sourceLabel: "SOC-WIN-01", target: "auth.corp.example", eventCount: 5, alertCount: 2 },
        topologyFixture.edges[0]!,
      ],
    };
    const collapsed = buildTopologyDomainView(groupedInput);
    expect(registrableDomainForTarget("auth.service.example.co.uk")).toBe("example.co.uk");
    expect(registrableDomainForTarget("203.0.113.10")).toBeNull();
    expect(collapsed.groups).toEqual([{ domain: "corp.example", targets: ["api.corp.example", "auth.corp.example"] }]);
    expect(collapsed.topology.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ endpointId: 1001, target: "corp.example", protocol: "DNS", eventCount: 8, alertCount: 3 }),
      expect.objectContaining({ target: "203.0.113.10" }),
    ]));
    const expanded = buildTopologyDomainView(groupedInput, new Set(["corp.example"]));
    expect(expanded.topology.edges.map((edge) => edge.target)).toEqual(expect.arrayContaining(["api.corp.example", "auth.corp.example", "203.0.113.10"]));
  });

  it("bounds the correlation canvas while preserving input-connected evidence first", () => {
    const base = correlationFixture.relationships[0]!;
    const relationships = Array.from({ length: 25 }, (_, index) => ({
      ...base,
      sourceValue: index === 24 ? correlationFixture.inputValue : `192.0.2.${index + 1}`,
      targetValue: `related-${index}.example.test`,
    }));
    const visible = correlationGraphRelationships({ ...correlationFixture, relationships });
    expect(visible).toHaveLength(CORRELATION_GRAPH_RELATIONSHIP_LIMIT);
    expect(correlationGraphRelationships({ ...correlationFixture, relationships }, CORRELATION_INLINE_RELATIONSHIP_LIMIT)).toHaveLength(CORRELATION_INLINE_RELATIONSHIP_LIMIT);
    expect(visible[0]).toMatchObject({ sourceValue: correlationFixture.inputValue, targetValue: "related-24.example.test" });
    expect(correlationGraphMinHeight(new Map([
      ["correlation:IP:input", { x: 0, y: 0 }],
      ["correlation:DOMAIN:last", { x: 0, y: 900 }],
    ]))).toBeGreaterThan(1_000);
  });

  it("reserves a readable label lane between topology ranks", () => {
    const positions = layoutTopologyNodes(topologyFixture);
    const source = positions.get("endpoint:1001");
    const target = positions.get("target:203.0.113.10");
    expect(source).toBeDefined();
    expect(target).toBeDefined();
    expect(target!.x - source!.x).toBeGreaterThanOrEqual(360);
    const labelPositions = [...layoutTopologyEdgeLabels(groupTopologyEdges(topologyFixture), positions).values()];
    const labelLanes = new Map<number, number[]>();
    for (const { xOffset, y } of labelPositions) labelLanes.set(xOffset, [...(labelLanes.get(xOffset) ?? []), y]);
    for (const lane of labelLanes.values()) {
      const labelYs = lane.sort((left, right) => left - right);
      for (let index = 1; index < labelYs.length; index += 1) expect(labelYs[index]! - labelYs[index - 1]!).toBeGreaterThanOrEqual(40);
    }
    const densePositions = new Map([...positions].map(([id, point]) => [id, { ...point, y: 0 }]));
    const denseLaneOffsets = new Set([...layoutTopologyEdgeLabels(groupTopologyEdges(topologyFixture), densePositions).values()].map(({ xOffset }) => xOffset));
    expect(denseLaneOffsets.size).toBe(2);
    expect(topologyEdgeVisualState(0)).toBe("observed-only");
    expect(topologyEdgeVisualState(1)).toBe("has-alerts");
  });

  it("grows the topology viewport before fitView would clip a tall node stack", () => {
    const positions = new Map([
      ["endpoint:1", { x: 0, y: 0 }],
      ["endpoint:2", { x: 0, y: 800 }],
    ]);
    const nodeOnlyHeight = topologyGraphMinHeight(positions);
    const labelAwareHeight = topologyGraphMinHeight(positions, new Map([["edge:1", { xOffset: 0, y: 1100 }]]));
    expect(nodeOnlyHeight).toBeGreaterThan(1_000);
    expect(labelAwareHeight).toBeGreaterThan(nodeOnlyHeight);
    expect(topologyGraphMinHeight(new Map())).toBe(420);
  });

  it("maps React Flow keyboard selection back to the synchronized topology context", () => {
    const node = document.createElement("div");
    node.className = "react-flow__node";
    node.dataset.id = "endpoint:1001";
    const nodeLabel = document.createElement("strong");
    node.append(nodeLabel);
    const edge = document.createElementNS("http://www.w3.org/2000/svg", "g");
    edge.classList.add("react-flow__edge");
    edge.dataset.id = "topology-group:1001:203.0.113.10";
    expect(topologySelectionFromElement(nodeLabel)).toEqual({ kind: "NODE", id: "endpoint:1001" });
    expect(topologySelectionFromElement(edge)).toEqual({ kind: "EDGE_GROUP", id: "topology-group:1001:203.0.113.10" });
    expect(topologySelectionFromElement(null)).toBeNull();
    expect(correlationSelectionFromElement(nodeLabel)).toEqual({ kind: "NODE", id: "endpoint:1001" });
    expect(correlationSelectionFromElement(edge)).toEqual({ kind: "EDGE", id: "topology-group:1001:203.0.113.10" });
  });

  it("renders MITRE selection, Rules/Signals tabs, and a synchronized table fallback without bytesOut", async () => {
    const { container } = renderWithProviders(<IntelligenceContent dashboard={dashboardFixture} graphEnabled={false} topology={topologyFixture} />);
    expect(screen.getByRole("region", { name: "Intelligence" })).toHaveClass("intelligence-summary-rail");
    expect(container.querySelectorAll(".intelligence-summary-rail .kpi-card")).toHaveLength(0);
    expect(screen.getByRole("heading", { name: "MITRE matrix" })).toBeInTheDocument();
    const tactic = screen.getByRole("button", { name: "TA0002, Execution, 3 Alert(s)" });
    expect(tactic.querySelector(".mitre-code")).toHaveTextContent("TA0002");
    expect(tactic.querySelector(".mitre-name")).toHaveTextContent("Execution");
    expect(tactic.className).not.toMatch(/heat-/);
    expect(screen.getByRole("button", { name: "T1059, Command and Scripting Interpreter, 2 Alert(s)" })).toHaveAttribute("title", "T1059 · Command and Scripting Interpreter");
    fireEvent.click(tactic);
    const mitreInspector = screen.getByRole("complementary", { name: "Execution" });
    expect(within(mitreInspector).getByText("3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Signals" }));
    expect(screen.getByText("Domain · example.com")).toBeInTheDocument();
    expect(screen.getByText("Topology graph is disabled")).toBeInTheDocument();
    const topologyTable = screen.getByRole("table", { name: "Endpoint egress relationships" });
    expect(topologyTable.closest(".relationship-evidence-table")).toBeInTheDocument();
    expect(within(topologyTable).getByRole("columnheader", { name: "Destination" })).toBeInTheDocument();
    expect(screen.getByText("Unique Endpoint-to-destination relationships")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "SOC-WIN-01" }));
    expect(screen.getByText("TCP relationship")).toBeInTheDocument();
    const selectedRow = within(topologyTable).getByRole("button", { name: "SOC-WIN-01" }).closest("tr");
    expect(selectedRow).not.toBeNull();
    expect(within(selectedRow!).getByRole("link", { name: "5" })).toHaveAttribute("href", "/events?timePreset=CUSTOM&from=2026-07-15T00%3A00%3A00Z&to=2026-07-16T00%3A00%3A00Z&endpointId=1001");
    expect(within(selectedRow!).getByRole("link", { name: "2" })).toHaveAttribute("href", "/alerts?timePreset=CUSTOM&from=2026-07-15T00%3A00%3A00Z&to=2026-07-16T00%3A00%3A00Z&endpointId=1001");
    expect(screen.queryByText(/bytesOut/i)).not.toBeInTheDocument();
  });

  it("keeps dense topology limits in the large dialog and restores the embedded view to ten", async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntelligenceContent dashboard={null} graphEnabled={false} topology={topologyFixture} />);
    const topN = screen.getByRole("combobox", { name: "Top-N relationships" });
    const expandButton = screen.getByRole("button", { name: "Open Endpoint egress topology in large view" });
    expect(topN).toHaveValue("10");
    expect(expandButton).toHaveAttribute("aria-haspopup", "dialog");
    await user.selectOptions(topN, "25");
    const dialog = screen.getByRole("dialog", { name: "Endpoint egress topology — Large view" });
    expect(within(dialog).getByRole("combobox", { name: "Top-N relationships" })).toHaveValue("25");
    await user.click(within(dialog).getByRole("button", { name: "Close large Endpoint egress topology" }));
    expect(topN).toHaveValue("10");
    expect(expandButton).toHaveFocus();
  });

  it("orders current pipeline problems first and never represents a historical flow", () => {
    expect(buildPipelineSnapshot(healthFixture, ingestFixture).map((stage) => stage.id)).toEqual(["DETECTION", "STORAGE", "COLLECTION"]);
    renderWithProviders(<PipelineSnapshot health={healthFixture} ingest={ingestFixture} />);
    const collection = screen.getByRole("region", { name: "Multi-layer collection path table" });
    expect(within(collection).getAllByRole("row")).toHaveLength(10);
    expect(collection.querySelectorAll(".status-pill")).toHaveLength(0);
    const stages = within(screen.getByRole("list", { name: "Current pipeline snapshot" })).getAllByRole("listitem");
    expect(stages[0]).toHaveTextContent("Detection");
    expect(stages[0]).toHaveTextContent("Unavailable");
    expect(screen.getByText(/not an animated or stored historical flow/i)).toBeInTheDocument();
  });

  it("keeps each Intelligence source usable when the other source is unavailable", () => {
    const { rerender } = renderWithProviders(<IntelligenceContent dashboard={dashboardFixture} graphEnabled={false} topology={null} />);
    expect(screen.getByRole("heading", { name: "MITRE matrix" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Endpoint egress topology" })).not.toBeInTheDocument();
    rerender(<QueryClientProvider client={new QueryClient()}><AuthProvider><LocaleProvider><MemoryRouter><IntelligenceContent dashboard={null} graphEnabled={false} topology={{ ...topologyFixture, edges: [] }} /></MemoryRouter></LocaleProvider></AuthProvider></QueryClientProvider>);
    expect(screen.getByRole("heading", { name: "Endpoint egress topology" })).toBeInTheDocument();
    expect(screen.getByText("No egress relationships")).toBeInTheDocument();
  });

  it("keeps IP and Domain together with source-labelled correlation evidence", async () => {
    const edge = correlationFixture.relationships[0]!;
    const selection = { kind: "EDGE" as const, id: correlationEdgeId(edge) };
    expect(selectedCorrelationRelationship(correlationFixture, selection)).toEqual(edge);
    renderWithProviders(<CorrelationResult correlation={correlationFixture} graphEnabled={false} />);
    expect(screen.getByText("Correlation graph is disabled")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "IP and Domain relationship evidence" }).closest(".relationship-evidence-table")).toBeInTheDocument();
    expect(screen.getAllByText("8.8.8.8").length).toBeGreaterThan(0);
    expect(screen.getAllByText("dns.google").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "8.8.8.8" }));
    const inspector = screen.getByRole("complementary", { name: "PTR CANDIDATE" });
    expect(within(inspector).getAllByText("LIVE_DNS").length).toBeGreaterThan(0);
    expect(within(inspector).getByText(/8\.8\.8\.8 → dns\.google/)).toBeInTheDocument();
    const expandButton = screen.getByRole("button", { name: "Open IP and Domain correlation graph in large view" });
    await userEvent.click(expandButton);
    const dialog = screen.getByRole("dialog", { name: "IP and Domain correlation — Large view" });
    expect(dialog).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Close large IP and Domain correlation graph" }));
    expect(expandButton).toHaveFocus();
  });

  it("shows every Archive lifecycle state, explicit zero counts, and role permission boundaries", () => {
    const counts = archiveLifecycleCounts(archiveBuckets);
    expect(counts).toEqual([
      { status: "HOT", count: 0 },
      { status: "ARCHIVED", count: 1 },
      { status: "RESTORE_REQUESTED", count: 1 },
      { status: "RESTORED", count: 0 },
      { status: "RESTORE_FAILED", count: 1 },
      { status: "EXPIRED", count: 0 },
    ]);
    renderWithProviders(<ArchiveLifecycleBoard items={archiveBuckets} />);
    const lifecycle = screen.getByRole("list", { name: "Archive lifecycle" });
    expect(within(lifecycle).getAllByRole("listitem")).toHaveLength(6);
    expect(within(lifecycle).getByText("RESTORE_REQUESTED").closest("li")).toHaveTextContent("1");
    expect(within(lifecycle).getByText("RESTORED").closest("li")).toHaveTextContent("0");
    expect(canMutate("ADMIN")).toBe(true);
    expect(canMutate("ANALYST")).toBe(true);
    expect(canMutate("VIEWER")).toBe(false);
  });

  it("renders a complete zero-state Archive lifecycle board", () => {
    renderWithProviders(<ArchiveLifecycleBoard items={[]} />);
    const stages = within(screen.getByRole("list", { name: "Archive lifecycle" })).getAllByRole("listitem");
    expect(stages).toHaveLength(6);
    expect(stages.every((stage) => stage.textContent?.includes("0"))).toBe(true);
  });

  it("uses locale-stable ISO placeholders for English Archive date-time controls", () => {
    renderWithProviders(<ArchivesPage />);
    const from = screen.getByLabelText("From");
    const to = screen.getByLabelText("To");
    expect(from).toHaveAttribute("lang", "en-US");
    expect(from).toHaveAttribute("type", "text");
    expect(from).toHaveAttribute("placeholder", "YYYY-MM-DD HH:mm");
    expect(from).toHaveAttribute("pattern", "\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}");
    fireEvent.change(from, { target: { value: "2026-07-21 12:00" } });
    expect(from).toBeValid();
    expect(to).toHaveAttribute("lang", "en-US");
    expect(to).toHaveAttribute("type", "text");
    expect(to).toHaveAttribute("placeholder", "YYYY-MM-DD HH:mm");
  });

  it("keeps an invalid Archive date draft and only clears the URL filter for an empty value", () => {
    renderWithProviders(<ArchivesPage />, ["/operations/archives?from=2026-07-21T03%3A00%3A00.000Z"]);
    const from = screen.getByLabelText("From");

    fireEvent.change(from, { target: { value: "not-a-date" } });
    fireEvent.blur(from);

    expect(from).toHaveValue("not-a-date");
    expect(from).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Use YYYY-MM-DD HH:mm in your local time.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove From filter" })).toBeInTheDocument();

    fireEvent.change(from, { target: { value: "" } });
    fireEvent.blur(from);

    expect(from).toHaveValue("");
    expect(from).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByRole("button", { name: "Remove From filter" })).not.toBeInTheDocument();
  });
});

function renderWithProviders(children: React.ReactNode, initialEntries: string[] = ["/"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><AuthProvider><LocaleProvider><MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter></LocaleProvider></AuthProvider></QueryClientProvider>);
}

const dashboardFixture = {
  timeRange: { from: "2026-07-15T00:00:00Z", to: "2026-07-16T00:00:00Z" },
  alerts: {
    mitreTactics: [{ mitreTacticCode: "TA0002", mitreTacticName: "Execution", count: 3 }],
    mitreTechniques: [{ mitreTechniqueCode: "T1059", mitreTechniqueName: "Command and Scripting Interpreter", count: 2 }],
    topRules: [{ ruleCode: "PROC-001", ruleName: "Suspicious PowerShell", count: 4 }],
  },
  events: {
    topDomains: [{ domain: "example.com", count: 4 }],
    topRemoteIps: [{ remoteIp: "203.0.113.10", count: 3 }],
    topProcesses: [{ processName: "powershell.exe", count: 2 }],
  },
} as unknown as DashboardSummaryDto;

const topologyFixture: EgressTopologyDto = {
  from: "2026-07-15T00:00:00Z",
  to: "2026-07-16T00:00:00Z",
  nodes: [
    { endpointId: 1001, hostname: "SOC-WIN-01", status: "ONLINE", riskScore: 88, riskLevel: "HIGH", alertCount: 2 },
    { endpointId: 1002, hostname: "SOC-MAC-01", status: "ONLINE", riskScore: 12, riskLevel: "LOW", alertCount: 0 },
  ],
  edges: [
    { endpointId: 1001, sourceLabel: "SOC-WIN-01", target: "203.0.113.10", protocol: "TCP", eventCount: 5, alertCount: 2, lastSeenAt: "2026-07-15T03:00:00Z" },
    { endpointId: 1002, sourceLabel: "SOC-MAC-01", target: "example.com", protocol: "DNS", eventCount: 8, alertCount: 0, lastSeenAt: "2026-07-15T02:00:00Z" },
  ],
};

const correlationFixture: CorrelationDto = {
  inputValue: "8.8.8.8",
  inputType: "IP",
  from: "2026-07-15T00:00:00Z",
  to: "2026-07-16T00:00:00Z",
  related: [
    { value: "dns.google", valueType: "DOMAIN", sources: ["LIVE_DNS"] },
    { value: "observed.google", valueType: "DOMAIN", sources: ["OBSERVED_EVENTS"] },
  ],
  relationships: [
    { sourceValue: "8.8.8.8", sourceType: "IP", targetValue: "dns.google", targetType: "DOMAIN", relation: "PTR_CANDIDATE", sources: ["LIVE_DNS"] },
    { sourceValue: "observed.google", sourceType: "DOMAIN", targetValue: "8.8.8.8", targetType: "IP", relation: "RESOLVES_TO", sources: ["OBSERVED_EVENTS"] },
  ],
};

const healthFixture: OperationsHealthDto = {
  checkedAt: "2026-07-15T04:00:00Z",
  status: "DEGRADED",
  services: [
    { service: "Backend API", status: "HEALTHY", latencyMs: 4, detail: "ready" },
    { service: "Kafka", status: "HEALTHY", latencyMs: 5, detail: "ready" },
    { service: "PostgreSQL", status: "HEALTHY", latencyMs: 3, detail: "ready" },
    { service: "ClickHouse", status: "DEGRADED", latencyMs: 18, detail: "slow" },
    { service: "S3", status: "HEALTHY", latencyMs: 8, detail: "ready" },
  ],
  workers: [{ worker: "detection", groupId: "detection-v1", topic: "telemetry.validated", status: "OFFLINE", memberCount: 0, lag: 7, detail: "no member" }],
};

const ingestFixture: IngestSummaryDto = {
  timeRange: { from: "2026-07-15T00:00:00Z", to: "2026-07-16T00:00:00Z" },
  events: { ingestedCount: 20, latestIngestedAt: "2026-07-15T03:59:00Z", ratePerMinute: 1.2 },
  eventFailures: { failedCount: 1, oldestFailedAt: "2026-07-15T01:00:00Z", ratePerMinute: 0.1, reprocessedCount: 0, reprocessFailedCount: 0 },
  storage: { clickhouseHotBucketCount: 2, glacierArchivedBucketCount: 1, restoringBucketCount: 1, restoredBucketCount: 0, failedBucketCount: 0, expiredBucketCount: 0 },
};

const archiveBuckets: ArchiveBucketDto[] = [
  archiveBucket("ARCHIVED", "s3://archive/1"),
  archiveBucket("RESTORE_REQUESTED", "s3://archive/2"),
  archiveBucket("RESTORE_FAILED", "s3://archive/3"),
];

function archiveBucket(storageStatus: ArchiveBucketDto["storageStatus"], storagePath: string): ArchiveBucketDto {
  return {
    endpointId: 1001,
    bucketStartAt: "2026-07-15T00:00:00Z",
    bucketEndAt: "2026-07-15T01:00:00Z",
    storageBackend: "S3",
    storageClass: "GLACIER_FLEXIBLE_RETRIEVAL",
    storageStatus,
    storagePath,
    eventCount: 10,
    sizeBytes: 100,
    checksumSha256: null,
    archivedAt: "2026-07-15T02:00:00Z",
    archiveVerifiedAt: "2026-07-15T02:10:00Z",
    restoreRequestedAt: storageStatus === "RESTORE_REQUESTED" ? "2026-07-15T03:00:00Z" : null,
    restoredAt: null,
    restoreExpiresAt: null,
    lastError: storageStatus === "RESTORE_FAILED" ? "retrieval failed" : null,
  };
}
