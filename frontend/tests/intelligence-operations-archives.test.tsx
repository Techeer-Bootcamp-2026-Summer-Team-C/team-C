import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../src/auth/AuthContext";
import type {
  ArchiveBucketDto,
  CorrelationDto,
  DashboardSummaryDto,
  EgressTopologyDto,
  IngestSummaryDto,
  OperationsHealthDto,
} from "../src/contracts";
import {
  archiveLifecycleCounts,
  buildPipelineSnapshot,
  correlationEdgeId,
  filterTopology,
  groupTopologyEdges,
  selectedCorrelationRelationship,
  selectedTopologyEdgeGroup,
  topologyEdgeGroupId,
  topologyGraphEnabled,
} from "../src/features/intelligenceOperations";
import { LocaleProvider } from "../src/i18n/LocaleContext";
import { ArchiveLifecycleBoard } from "../src/pages/ArchivesPage";
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

  it("renders MITRE selection, Rules/Signals tabs, and a synchronized table fallback without bytesOut", async () => {
    const { container } = renderWithProviders(<IntelligenceContent dashboard={dashboardFixture} graphEnabled={false} topology={topologyFixture} />);
    expect(screen.getByRole("region", { name: "Intelligence" })).toHaveClass("intelligence-summary-rail");
    expect(container.querySelectorAll(".intelligence-summary-rail .kpi-card")).toHaveLength(0);
    expect(screen.getByRole("heading", { name: "MITRE matrix" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /TA0002/ }));
    const mitreInspector = screen.getByRole("complementary", { name: "Execution" });
    expect(within(mitreInspector).getByText("3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Signals" }));
    expect(screen.getByText("Domain · example.com")).toBeInTheDocument();
    expect(screen.getByText("Topology graph is disabled")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "SOC-WIN-01" }));
    expect(screen.getByText("TCP relationship")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "2" })).toHaveAttribute("href", expect.stringContaining("/alerts?"));
    expect(screen.queryByText(/bytesOut/i)).not.toBeInTheDocument();
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
    expect(screen.getAllByText("8.8.8.8").length).toBeGreaterThan(0);
    expect(screen.getAllByText("dns.google").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "8.8.8.8" }));
    const inspector = screen.getByRole("complementary", { name: "PTR CANDIDATE" });
    expect(within(inspector).getAllByText("LIVE_DNS").length).toBeGreaterThan(0);
    expect(within(inspector).getByText(/8\.8\.8\.8 → dns\.google/)).toBeInTheDocument();
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
});

function renderWithProviders(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><AuthProvider><LocaleProvider><MemoryRouter>{children}</MemoryRouter></LocaleProvider></AuthProvider></QueryClientProvider>);
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
