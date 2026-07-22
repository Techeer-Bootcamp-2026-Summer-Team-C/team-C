import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { DetectionActivityTable } from "../src/components/charts";
import { EdrStateSummary } from "../src/components/ui";
import { AuthProvider } from "../src/auth/AuthContext";
import { api } from "../src/api/endpoints";
import { OverviewDashboard, OVERVIEW_BLOCK_IDS, type OverviewDashboardData } from "../src/features/overview/OverviewDashboard";
import { AlertSeverityDonut } from "../src/features/overview/AlertSeverityDonut";
import { EndpointScopePicker } from "../src/features/overview/EndpointScopePicker";
import DetectionActivityPanel from "../src/features/overview/DetectionActivityPanel";
import { buildDetectionActivityModel } from "../src/features/overview/overviewChartModel";
import { LocaleProvider } from "../src/i18n/LocaleContext";
import type { EndpointDto, IncidentDto } from "../src/contracts";
import { OverviewPage, readOverviewEndpointId } from "../src/pages/OverviewPage";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { useTheme } from "../src/theme/ThemeProvider";
import { init as initECharts } from "echarts/core";

vi.mock("echarts/core", () => ({
  init: vi.fn(() => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    dispatchAction: vi.fn(),
  })),
  use: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

describe("overview fixed dashboard", () => {
  it("renders the ten large-screen monitoring blocks in DOM order", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><MemoryRouter><OverviewDashboard data={overviewData()} /></MemoryRouter></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);
    expect([...container.querySelectorAll("[data-overview-block]")].map((block) => block.getAttribute("data-overview-block"))).toEqual([
      "edr-state",
      "kpi-alerts",
      "kpi-critical-alerts",
      "kpi-high-risk-endpoints",
      "kpi-open-incidents",
      "detection-activity",
      "alert-severity",
      "fleet-distribution",
      "highest-risk-endpoints",
      "incident-queue",
    ]);
    expect(OVERVIEW_BLOCK_IDS).toHaveLength(10);
    expect(screen.getByText("Observed signal stream", { selector: "strong" })).toHaveAttribute("title", "Observed signal stream");
    expect(screen.queryByRole("button", { name: /edit dashboard|reset default|save/i })).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: /Threat level: 78 \/ 100, Red/i })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: /Collection health: 61 \/ 100, Yellow/i })).toBeInTheDocument();
    expect(screen.getByText("High Endpoint Risk")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Critical alerts1/i })).toHaveAttribute("href", "/alerts?severity=CRITICAL&timePreset=LATEST_24H");
    expect(screen.getByRole("link", { name: /Total alerts3/i })).toHaveClass("accent");
    expect(screen.getByRole("link", { name: /Critical alerts1/i })).toHaveClass("critical");
    expect(screen.getByRole("link", { name: /HIGH-level endpoints1/i })).toHaveClass("high");
    expect(screen.getByRole("link", { name: /Open incidents1/i })).toHaveClass("info");
    expect(screen.getByRole("heading", { name: "Fleet distribution" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "High: 1 / 1" })).toHaveAttribute("aria-valuenow", "1");
    expect(screen.getByRole("img", { name: /All sensors: 1 healthy, 0 degraded, 0 unavailable, 1 total/i })).toBeInTheDocument();
    const processSensor = screen.getByRole("list", { name: /Process: 1 healthy, 0 degraded, 0 unavailable, 1 total/i });
    expect(within(processSensor).getByText("Healthy")).toBeInTheDocument();
    expect(within(processSensor).getByText("Degraded")).toBeInTheDocument();
    expect(within(processSensor).getByText("Unavailable")).toBeInTheDocument();
    expect(within(processSensor).getByText("1")).toBeInTheDocument();
    expect(within(processSensor).getAllByText("0")).toHaveLength(2);
  });

  it("shows explicit Fleet distribution empty states without inventing zero snapshots", () => {
    const data = overviewData();
    data.endpoints = {
      ...data.endpoints!,
      risk: { ...data.endpoints!.risk, byLevel: [] },
      sensorHealth: [],
    };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><MemoryRouter>
      <OverviewDashboard data={data} />
    </MemoryRouter></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    const fleetBlock = container.querySelector<HTMLElement>('[data-overview-block="fleet-distribution"]');
    expect(fleetBlock).not.toBeNull();
    expect(within(fleetBlock as HTMLElement).getByText("No Endpoint risk snapshot is available.")).toBeInTheDocument();
    expect(within(fleetBlock as HTMLElement).getByText("No Sensor Health snapshots are available.")).toBeInTheDocument();
    expect(within(fleetBlock as HTMLElement).queryByRole("progressbar", { name: /Critical:/i })).not.toBeInTheDocument();
    expect(within(fleetBlock as HTMLElement).queryByRole("img")).not.toBeInTheDocument();
  });

  it("preserves preset and custom time scope only on time-scoped KPI drilldowns", () => {
    const data = overviewData();
    data.selectedEndpointId = 2;
    data.timeRange = { timePreset: "LATEST_15M" };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><MemoryRouter><OverviewDashboard data={data} /></MemoryRouter></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    expectDrilldownQuery(/Total alerts3/i, { endpointId: "2", timePreset: "LATEST_15M" });
    expectDrilldownQuery(/Critical alerts1/i, { endpointId: "2", severity: "CRITICAL", timePreset: "LATEST_15M" });
    expectDrilldownQuery(/Open incidents1/i, { endpointId: "2", status: "OPEN", timePreset: "LATEST_15M" });
    const endpointUrl = linkUrl(/HIGH-level endpoints1/i);
    expect(endpointUrl.searchParams.get("endpointIds")).toBe("2");
    expect(endpointUrl.searchParams.has("timePreset")).toBe(false);
    expect(endpointUrl.searchParams.has("from")).toBe(false);
    expect(endpointUrl.searchParams.has("to")).toBe(false);

    data.timeRange = { timePreset: "CUSTOM", from: "2026-07-15T00:00:00Z", to: "2026-07-15T06:30:00Z" };
    rerender(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><MemoryRouter><OverviewDashboard data={data} /></MemoryRouter></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);
    expectDrilldownQuery(/Total alerts3/i, {
      endpointId: "2",
      from: "2026-07-15T00:00:00Z",
      timePreset: "CUSTOM",
      to: "2026-07-15T06:30:00Z",
    });
  });

  it("does not expose dashboard layout client methods", () => {
    expect("dashboardLayout" in api).toBe(false);
    expect("saveDashboardLayout" in api).toBe(false);
    expect("resetDashboardLayout" in api).toBe(false);
  });

  it("keeps zero and empty EDR diagnostics truthful", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><MemoryRouter>
      <EdrStateSummary state={{
        status: "GREEN",
        score: 0,
        threatLevel: { status: "GREEN", score: 0, reasonCodes: [] },
        collectionHealth: { status: "GREEN", score: 0, reasonCodes: [] },
        reasonCodes: [],
        criticalRiskEndpointCount: 0,
        highRiskEndpointCount: 0,
        highestEndpointRiskScore: null,
        calculatedAt: "2026-07-15T00:00:00Z",
      }} />
    </MemoryRouter></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    expect(screen.getByRole("region", { name: "Current EDR state" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Threat level: 0 / 100, Green" })).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByRole("progressbar", { name: "Collection health: 0 / 100, Green" })).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText("No active risk reasons")).toBeInTheDocument();
  });

  it("sorts server-provided activity series without filling a missing bucket and exposes the table fallback", () => {
    const events = [{ bucketStartAt: "2026-07-15T02:00:00Z", count: 12 }, { bucketStartAt: "2026-07-15T00:00:00Z", count: 8 }];
    const alerts = [{ bucketStartAt: "2026-07-15T01:00:00Z", count: 4 }];
    const incidents = [{ bucketStartAt: "2026-07-15T02:00:00Z", openCount: 2, closedCount: 1 }];
    window.sessionStorage.setItem("edr.authSession", JSON.stringify({
      token: "overview-test-token",
      user: { userId: 1, loginId: "admin", name: "Administrator", role: "ADMIN", status: "ACTIVE", locale: "EN" },
      expiresAt: Date.now() + 60_000,
    }));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><DetectionActivityTable alerts={alerts} events={events} incidents={incidents} /></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    expect(screen.getByRole("table", { name: "Events" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Alerts" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Incidents" })).toBeInTheDocument();
    const model = buildDetectionActivityModel(events, alerts, incidents);
    expect(model.series[0]?.points.map(([timestamp]) => new Date(timestamp).toISOString())).toEqual([
      "2026-07-15T00:00:00.000Z",
      "2026-07-15T01:00:00.000Z",
      "2026-07-15T02:00:00.000Z",
    ]);
    expect(model.series[0]?.points.map(([, value]) => value)).toEqual([8, null, 12]);
    expect(model.series[1]?.points.map(([, value]) => value)).toEqual([null, 4, null]);
    expect(model.timestamps).toHaveLength(3);
  });

  it("announces missing latest buckets without fabricating zero and clears an invalid chart selection", async () => {
    setAuthSession();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container, rerender } = render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider>
      <DetectionActivityPanel
        alerts={[{ bucketStartAt: "2026-07-15T01:00:00Z", count: 4 }]}
        events={[{ bucketStartAt: "2026-07-15T00:00:00Z", count: 8 }]}
        incidents={[{ bucketStartAt: "2026-07-15T01:00:00Z", openCount: 2, closedCount: 1 }]}
      />
    </LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    expect(screen.getByText("Latest server buckets: Events None, Alerts 4, Open incidents 2.")).toBeInTheDocument();
    const bucketSelect = screen.getByRole("combobox", { name: "Detection activity time buckets" });
    const firstBucket = within(bucketSelect).getAllByRole("option")[1];
    expect(firstBucket).toBeDefined();
    fireEvent.change(bucketSelect, { target: { value: (firstBucket as HTMLOptionElement).value } });
    expect(container.querySelector(".chart-selected-value")).not.toBeNull();

    rerender(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider>
      <DetectionActivityPanel
        alerts={[]}
        events={[{ bucketStartAt: "2026-07-15T03:00:00Z", count: 11 }]}
        incidents={[]}
      />
    </LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    await waitFor(() => expect(container.querySelector(".chart-selected-value")).toBeNull());
    expect(screen.getByRole("combobox", { name: "Detection activity time buckets" })).toHaveValue("");
  });

  it("updates ECharts options from semantic tokens without recreating the chart", async () => {
    setAuthSession();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const initMock = vi.mocked(initECharts);
    const callsBeforeRender = initMock.mock.calls.length;
    render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider>
      <ThemeChartHarness />
    </LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    await waitFor(() => expect(initMock.mock.calls.length).toBeGreaterThan(callsBeforeRender));
    const callsAfterMount = initMock.mock.calls.length;
    const setOptionMock = vi.mocked(initMock.mock.results.at(-1)!.value.setOption);
    const optionCallsAfterMount = setOptionMock.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "change chart theme" }));
    await waitFor(() => expect(setOptionMock.mock.calls.length).toBeGreaterThan(optionCallsAfterMount));
    expect(initMock.mock.calls.length).toBe(callsAfterMount);
  });

  it("renders a fixed-order severity donut with count, percentage, and safe zero totals", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider>
      <AlertSeverityDonut label="Total alerts" rows={[{ severity: "HIGH", count: 25 }, { severity: "CRITICAL", count: 5 }]} total={100} />
    </LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);
    expect(screen.getByRole("figure", { name: "Total alerts" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").map((row) => row.textContent)).toEqual(["Critical55%", "High2525%", "Medium00%", "Low00%"]);
    expect(document.querySelectorAll(".severity-donut-segment")).toHaveLength(2);

    rerender(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider>
      <AlertSeverityDonut label="Total alerts" rows={[]} total={0} />
    </LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);
    expect(screen.getAllByText("0%")).toHaveLength(4);
    expect(document.querySelectorAll(".severity-donut-segment")).toHaveLength(0);
  });

  it("searches Endpoint scope in 20-row pages and emits the selected id", async () => {
    window.sessionStorage.setItem("edr.authSession", JSON.stringify({
      token: "overview-test-token",
      user: { userId: 1, loginId: "admin", name: "Administrator", role: "ADMIN", status: "ACTIVE", locale: "EN" },
      expiresAt: Date.now() + 60_000,
    }));
    const onChange = vi.fn();
    const endpointOptions = [
      { endpointId: 1, hostname: "SOC-WIN-01", status: "ONLINE", risk: { level: "HIGH", score: 71 } } as EndpointDto,
      { endpointId: 2, hostname: "FINANCE-MAC-02", status: "ONLINE", risk: { level: "CRITICAL", score: 91 } } as EndpointDto,
    ];
    const endpointsSpy = vi.spyOn(api, "endpoints").mockResolvedValue({ data: { items: endpointOptions, page: 1, size: 20, total: 42 }, meta: { requestId: "req_overview_scope" } });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider>
      <EndpointScopePicker onChange={onChange} selectedEndpointId={undefined} />
    </LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    expect(screen.getByText("Endpoint scope", { selector: ".overview-endpoint-label" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Endpoint scope" }));
    expect(await screen.findByRole("option", { name: /FINANCE-MAC-02/ })).toBeInTheDocument();
    expect(endpointsSpy).toHaveBeenCalledWith({ page: 1, size: 20, sortBy: "riskScore", sortOrder: "desc" }, expect.any(AbortSignal));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "finance" } });
    await waitFor(() => expect(endpointsSpy).toHaveBeenCalledWith({ page: 1, size: 20, q: "finance", sortBy: "riskScore", sortOrder: "desc" }, expect.any(AbortSignal)));
    fireEvent.click(await screen.findByRole("option", { name: /FINANCE-MAC-02/ }));
    fireEvent.click(screen.getByRole("button", { name: "Endpoint scope" }));
    fireEvent.click(screen.getByRole("option", { name: "All endpoints" }));
    expect(onChange).toHaveBeenNthCalledWith(1, 2);
    expect(onChange).toHaveBeenNthCalledWith(2, undefined);
    expect(JSON.stringify(endpointsSpy.mock.calls)).not.toContain('"size":500');
  });

  it("preserves outside pointer focus and restores trigger focus for keyboard close", async () => {
    setAuthSession();
    vi.spyOn(api, "endpoints").mockResolvedValue(success({ items: [], page: 1, size: 20, total: 0 }));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider>
      <button type="button">Outside action</button>
      <EndpointScopePicker onChange={vi.fn()} selectedEndpointId={undefined} />
    </LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    const trigger = screen.getByRole("button", { name: "Endpoint scope" });
    const outside = screen.getByRole("button", { name: "Outside action" });
    fireEvent.click(trigger);
    await screen.findByRole("combobox");
    outside.focus();
    fireEvent.pointerDown(outside);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Endpoint scope" })).not.toBeInTheDocument());
    expect(outside).toHaveFocus();

    fireEvent.click(trigger);
    const input = await screen.findByRole("combobox");
    fireEvent.keyDown(input, { key: "Escape" });
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(screen.queryByRole("dialog", { name: "Endpoint scope" })).not.toBeInTheDocument();
  });

  it("keeps a successful queue visible when its sibling section fails", () => {
    const data = overviewData();
    data.incidentQueue = [{
      incidentId: 9,
      title: "Suspicious PowerShell",
      severity: "HIGH",
      status: "OPEN",
      alertCount: 3,
      lastDetectedAt: "2026-07-15T03:00:00Z",
    } as IncidentDto];
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><MemoryRouter>
      <OverviewDashboard data={data} queueState={{
        endpoints: { pending: false, error: new Error("endpoint queue failed"), stale: false, onRetry: vi.fn() },
        incidents: { pending: false, error: null, stale: false, onRetry: vi.fn() },
      }} />
    </MemoryRouter></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Incident queue" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Suspicious PowerShell" })).toHaveAttribute("href", "/incidents/9");
    expect(container.querySelector(".selected-row")).toBeNull();
  });

  it("renders compact investigation lists without redundant risk progress or table overflow", () => {
    const data = overviewData();
    data.topEndpoints = [{
      endpointId: 7,
      agentId: "agent-with-a-long-readable-identifier",
      hostname: "RETIRED-LAB-ENDPOINT-WITH-A-LONG-HOSTNAME",
      risk: { score: 91, level: "CRITICAL", activeAlertCount: 18, openIncidentCount: 3 },
    } as EndpointDto];
    data.incidentQueue = [{
      incidentId: 9,
      title: "ENCODED POWERSHELL WITH A LONG INVESTIGATION TITLE",
      severity: "HIGH",
      status: "OPEN",
      alertCount: 3,
      lastDetectedAt: "2026-07-15T03:00:00Z",
    } as IncidentDto];
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><MemoryRouter>
      <OverviewDashboard data={data} />
    </MemoryRouter></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    const riskList = screen.getByRole("list", { name: "Highest-risk endpoints" });
    expect(within(riskList).queryByRole("progressbar")).not.toBeInTheDocument();
    expect(within(riskList).queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "RETIRED-LAB-ENDPOINT-WITH-A-LONG-HOSTNAME" })).toHaveAttribute("title", "RETIRED-LAB-ENDPOINT-WITH-A-LONG-HOSTNAME");
    expect(screen.getByRole("list", { name: "Incident queue" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ENCODED POWERSHELL WITH A LONG INVESTIGATION TITLE" })).toHaveAttribute("title", "ENCODED POWERSHELL WITH A LONG INVESTIGATION TITLE");
  });

  it("keeps Dashboard Summary panels visible when Endpoint Summary initially fails", async () => {
    setAuthSession();
    const data = overviewData();
    const dashboardSpy = vi.spyOn(api, "dashboard").mockResolvedValue(success(data.dashboard!));
    vi.spyOn(api, "endpointSummary").mockRejectedValue(new Error("endpoint summary failed"));
    vi.spyOn(api, "ingestSummary").mockResolvedValue(success(ingestSummary()));
    vi.spyOn(api, "endpoints").mockResolvedValue(success({ items: [], page: 1, size: 5, total: 0 }));
    vi.spyOn(api, "incidents").mockResolvedValue(success({ items: [], page: 1, size: 5, total: 0 }));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><MemoryRouter>
      <OverviewPage />
    </MemoryRouter></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    await waitFor(() => expect(dashboardSpy).toHaveBeenCalled());
    await waitFor(() => expect(queryClient.getQueryData(["dashboard", { timePreset: "LATEST_24H", interval: "1h" }])).toEqual(success(data.dashboard!)));
    expect(await screen.findByRole("region", { name: "Fixed Overview dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard settings" })).toHaveAttribute("href", "/dashboards");
    expect(screen.queryByText("ACTIVE LAYOUT")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Total alerts3/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open incidents1/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Alert severity" })).toBeInTheDocument();
    const endpointKpiBlock = container.querySelector<HTMLElement>('[data-overview-block="kpi-high-risk-endpoints"]');
    expect(endpointKpiBlock).not.toBeNull();
    expect(within(endpointKpiBlock as HTMLElement).getByRole("alert")).toBeInTheDocument();
    expect(container.querySelectorAll("[data-overview-block]")).toHaveLength(10);
    expect(screen.getByText(/Successful dashboard sections remain available/i)).toBeInTheDocument();
  });

  it("keeps Endpoint Summary panels visible when Dashboard Summary initially fails", async () => {
    setAuthSession();
    const data = overviewData();
    vi.spyOn(api, "dashboard").mockRejectedValue(new Error("dashboard summary failed"));
    const endpointSummarySpy = vi.spyOn(api, "endpointSummary").mockResolvedValue(success(data.endpoints!));
    vi.spyOn(api, "ingestSummary").mockResolvedValue(success(ingestSummary()));
    vi.spyOn(api, "endpoints").mockResolvedValue(success({ items: [], page: 1, size: 5, total: 0 }));
    vi.spyOn(api, "incidents").mockResolvedValue(success({ items: [], page: 1, size: 5, total: 0 }));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><MemoryRouter>
      <OverviewPage />
    </MemoryRouter></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

    await waitFor(() => expect(endpointSummarySpy).toHaveBeenCalled());
    await waitFor(() => expect(queryClient.getQueryData(["endpoint-summary", { timePreset: "LATEST_24H" }])).toEqual(success(data.endpoints!)));
    expect(await screen.findByRole("region", { name: "Fixed Overview dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /HIGH-level endpoints1/i })).toBeInTheDocument();
    const alertKpiBlock = container.querySelector<HTMLElement>('[data-overview-block="kpi-alerts"]');
    expect(alertKpiBlock).not.toBeNull();
    expect(within(alertKpiBlock as HTMLElement).getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Fleet distribution" })).toBeInTheDocument();
    expect(container.querySelectorAll("[data-overview-block]")).toHaveLength(10);
    expect(screen.getByText(/Successful dashboard sections remain available/i)).toBeInTheDocument();
  });

  it("reads only positive integer endpointId values from the Overview URL", () => {
    expect(readOverviewEndpointId(new URLSearchParams("endpointId=2"))).toBe(2);
    expect(readOverviewEndpointId(new URLSearchParams("endpointId=0"))).toBeUndefined();
    expect(readOverviewEndpointId(new URLSearchParams("endpointId=all"))).toBeUndefined();
  });
});

function overviewData(): OverviewDashboardData {
  return {
    dashboard: {
      edrState: {
        status: "YELLOW", score: 42,
        threatLevel: { status: "RED", score: 78, reasonCodes: ["HIGH_ENDPOINT_RISK"] },
        collectionHealth: { status: "YELLOW", score: 61, reasonCodes: ["INGEST_DELAYED"] },
        reasonCodes: ["HIGH_ENDPOINT_RISK"], calculatedAt: "2026-07-15T00:00:00Z",
      },
      alerts: { totalCount: 3, bySeverity: [{ severity: "CRITICAL", count: 1 }], timeSeries: [] },
      events: { timeSeries: [] },
      incidents: { openCount: 1, timeSeries: [] },
    } as unknown as OverviewDashboardData["dashboard"],
    endpoints: {
      totalCount: 1,
      risk: { highRiskEndpointCount: 1, criticalRiskEndpointCount: 0, highestScore: 72, calculatedAt: "2026-07-15T00:00:00Z", byLevel: [{ level: "HIGH", count: 1 }] },
      sensorHealth: [{ sensor: "PROCESS", status: "HEALTHY", count: 1 }],
    } as unknown as OverviewDashboardData["endpoints"],
    topEndpoints: [],
    incidentQueue: [],
    selectedEndpointId: undefined,
    timeRange: { timePreset: "LATEST_24H" },
  };
}

function linkUrl(name: RegExp): URL {
  const href = screen.getByRole("link", { name }).getAttribute("href");
  expect(href).not.toBeNull();
  return new URL(href as string, "http://overview.test");
}

function expectDrilldownQuery(name: RegExp, expected: Record<string, string>) {
  const url = linkUrl(name);
  for (const [key, value] of Object.entries(expected)) expect(url.searchParams.get(key)).toBe(value);
}

function setAuthSession() {
  window.sessionStorage.setItem("edr.authSession", JSON.stringify({
    token: "overview-test-token",
    user: { userId: 1, loginId: "admin", name: "Administrator", role: "ADMIN", status: "ACTIVE", locale: "EN" },
    expiresAt: Date.now() + 60_000,
  }));
}

function success<Data>(data: Data) {
  return { data, meta: { requestId: "req_overview_test" } };
}

function ingestSummary() {
  return {
    timeRange: { from: "2026-07-15T00:00:00Z", to: "2026-07-16T00:00:00Z" },
    events: { ingestedCount: 3, ratePerMinute: 1, latestIngestedAt: "2026-07-16T00:00:00Z" },
    eventFailures: { failedCount: 0, ratePerMinute: 0, reprocessedCount: 0, reprocessFailedCount: 0, oldestFailedAt: null },
    storage: { clickhouseHotBucketCount: 1, restoredBucketCount: 0, glacierArchivedBucketCount: 0, restoringBucketCount: 0, failedBucketCount: 0, expiredBucketCount: 0 },
  };
}

function ThemeChartHarness() {
  const { toggleTheme } = useTheme();
  return <>
    <button onClick={toggleTheme} type="button">change chart theme</button>
    <DetectionActivityPanel
      alerts={[{ bucketStartAt: "2026-07-15T01:00:00Z", count: 4 }]}
      events={[{ bucketStartAt: "2026-07-15T01:00:00Z", count: 8 }]}
      incidents={[{ bucketStartAt: "2026-07-15T01:00:00Z", openCount: 2, closedCount: 0 }]}
    />
  </>;
}
