import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../src/auth/AuthContext";
import { IncidentGraph, layoutInvestigationNodes } from "../src/components/IncidentGraph";
import { IncidentInvestigation } from "../src/components/IncidentInvestigation";
import type { AttackTimelineDto, IncidentInvestigationDto, InvestigationNodeDto } from "../src/contracts";
import {
  incidentDetailUrl,
  incidentGraphEnabled,
  incidentQueueQuery,
  selectedProcessPid,
  selectionMatchesTimelineItem,
} from "../src/features/incidentInvestigation";
import { LocaleProvider } from "../src/i18n/LocaleContext";

afterEach(cleanup);

describe("Incident investigation contract", () => {
  it("preserves the Incident list context, defaults to OPEN, and replaces stale selected state", () => {
    const params = new URLSearchParams("timePreset=CUSTOM&from=2026-07-14T00%3A00%3A00Z&to=2026-07-15T00%3A00%3A00Z&severity=CRITICAL&endpointId=1001&sortOrder=asc&selected=7");
    expect(incidentQueueQuery(params)).toEqual({
      timePreset: "CUSTOM",
      from: "2026-07-14T00:00:00Z",
      to: "2026-07-15T00:00:00Z",
      status: "OPEN",
      severity: "CRITICAL",
      endpointId: 1001,
      sortOrder: "asc",
      page: 1,
      size: 500,
    });
    expect(incidentDetailUrl(42, params)).toContain("selected=42");
    expect(incidentGraphEnabled("false")).toBe(false);
    expect(incidentGraphEnabled("0")).toBe(false);
    expect(incidentGraphEnabled("true")).toBe(true);
  });

  it("keeps partial/archive evidence accessible through the table fallback", () => {
    const onSelect = vi.fn();
    const investigation = fixture({ partial: true, truncated: true, warnings: [{ code: "ARCHIVE_NOT_READY", message: "Archived Event is not restored.", eventId: "event-1", endpointId: 1001, occurredAt: NOW }] });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><AuthProvider><LocaleProvider><MemoryRouter><IncidentInvestigation graphEnabled={false} investigation={investigation} onSelect={onSelect} selection={null} /></MemoryRouter></LocaleProvider></AuthProvider></QueryClientProvider>);
    expect(screen.getByText("Graph rendering is disabled by feature flag")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open archive operations" })).toHaveAttribute("href", "/operations/archives");
    const evidence = screen.getByRole("table", { name: "Observed evidence" });
    expect(evidence.closest(".relationship-evidence-table")).toBeInTheDocument();
    expect(evidence.closest(".investigation-panel")).toBeInTheDocument();
    expect(within(evidence).getAllByRole("row")).toHaveLength(2);
    expect(within(evidence).getByText("Observed")).toBeInTheDocument();
    fireEvent.click(within(evidence).getByRole("button", { name: "Contains" }));
    expect(onSelect).toHaveBeenCalledWith({ kind: "EDGE", id: "edge-1" });
    expect(screen.queryByRole("application", { name: "Incident investigation graph" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open Observed nodes in large view" }));
    expect(screen.getByRole("dialog", { name: "Observed nodes · expanded investigation" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close expanded investigation" }));
    expect(screen.queryByRole("dialog", { name: "Observed nodes · expanded investigation" })).not.toBeInTheDocument();
  });

  it("synchronizes graph context with timeline evidence and Process Tree PID", () => {
    const investigation = fixture();
    const timeline: AttackTimelineDto = { incidentId: 1, endpointId: 1001, items: [{ itemType: "ALERT", occurredAt: NOW, title: "Encoded PowerShell", summary: "Observed alert", severity: "HIGH", eventType: null, eventId: null, alertId: 11, incidentId: 1, endpointId: 1001 }] };
    expect(selectionMatchesTimelineItem({ kind: "EDGE", id: "edge-1" }, investigation, timeline.items[0]!)).toBe(true);
    expect(selectedProcessPid({ kind: "NODE", id: "process-55" }, investigation)).toBe(55);
  });

  it("lays out the full 250-node contract without dropping nodes", () => {
    const nodes = Array.from({ length: 250 }, (_, index) => node({ nodeId: `event-${index}`, nodeType: "EVENT", label: `Event ${index}`, eventId: `event-${index}` }));
    const positions = layoutInvestigationNodes({ nodes, edges: [] });
    expect(positions.size).toBe(250);
    expect([...positions.values()].every(({ x, y }) => Number.isFinite(x) && Number.isFinite(y))).toBe(true);
  });

  it("exports the graph component for the feature-gated dynamic chunk", () => {
    expect(IncidentGraph).toBeTypeOf("function");
  });
});

const NOW = "2026-07-15T01:00:00Z";

function fixture(overrides: Partial<IncidentInvestigationDto> = {}): IncidentInvestigationDto {
  const nodes = [
    node({ nodeId: "incident-1", nodeType: "INCIDENT", label: "Incident 1", incidentId: 1 }),
    node({ nodeId: "alert-11", nodeType: "ALERT", label: "Encoded PowerShell", incidentId: 1, alertId: 11, severity: "HIGH" }),
    node({ nodeId: "process-55", nodeType: "PROCESS", label: "powershell.exe", endpointId: 1001, pid: 55, processName: "powershell.exe" }),
  ];
  return {
    incidentId: 1,
    timeRange: { from: "2026-07-15T00:00:00Z", to: "2026-07-15T02:00:00Z" },
    nodes,
    edges: [{ edgeId: "edge-1", sourceNodeId: "incident-1", targetNodeId: "alert-11", relation: "CONTAINS", evidence: "OBSERVED", incidentId: 1, alertId: 11, eventId: null, observedAt: NOW }],
    nodeCount: nodes.length,
    edgeCount: 1,
    truncated: false,
    partial: false,
    warnings: [],
    fallback: { timelineAvailable: true, alertTableAvailable: true, eventTableAvailable: true },
    ...overrides,
  };
}

function node(overrides: Partial<InvestigationNodeDto> & Pick<InvestigationNodeDto, "nodeId" | "nodeType" | "label">): InvestigationNodeDto {
  return {
    endpointId: null,
    incidentId: null,
    alertId: null,
    eventId: null,
    pid: null,
    processName: null,
    destination: null,
    protocol: null,
    occurredAt: NOW,
    severity: null,
    eventType: null,
    riskScore: null,
    ...overrides,
  };
}
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
