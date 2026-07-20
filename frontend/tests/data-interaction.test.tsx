import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ApiError } from "../src/api/client";
import { AuthProvider } from "../src/auth/AuthContext";
import { ChartFrame, DataTable, FilterBar, Inspector, MasterDetail, Pagination, PartialFailureWarning, QueryFeedback, SortableHeader } from "../src/components/ui";
import { appliedFilterDescriptors, eventDetailSearch, hasInvalidEnum, hasInvalidPagination, hasInvalidPositiveInteger, hasInvalidText, removeListFilter, safeReturnPath, selectedSearch } from "../src/features/listInteractions";
import { LocaleProvider } from "../src/i18n/LocaleContext";
import { AlertsPage } from "../src/pages/AlertsPage";
import { ArchivesPage } from "../src/pages/ArchivesPage";
import { EndpointsPage } from "../src/pages/EndpointsPage";
import { EventsPage } from "../src/pages/EventsPage";
import { IncidentsPage } from "../src/pages/IncidentsPage";

const USER = { userId: 1, loginId: "admin", name: "Administrator", role: "ADMIN", status: "ACTIVE", locale: "EN" } as const;
const TIMESTAMP = "2026-07-15T03:00:00Z";

beforeEach(() => {
  sessionStorage.setItem("edr.authSession", JSON.stringify({ token: "interaction-token", user: USER, expiresAt: Date.now() + 60_000 }));
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => mockResponse(String(input))));
});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("list interaction utilities", () => {
  it("builds and removes applied filters without losing unrelated URL state", () => {
    const params = new URLSearchParams("timePreset=CUSTOM&from=2026-07-14T00%3A00%3A00Z&to=2026-07-15T00%3A00%3A00Z&status=OPEN&page=3&selected=11");
    expect(appliedFilterDescriptors(params, [{ key: "status", label: "Status" }, { key: "missing", label: "Missing" }])).toEqual([{ key: "status", label: "Status", value: "OPEN" }]);
    const removed = removeListFilter(params, "timePreset");
    expect(removed.has("timePreset")).toBe(false);
    expect(removed.has("from")).toBe(false);
    expect(removed.has("to")).toBe(false);
    expect(removed.has("page")).toBe(false);
    expect(removed.get("status")).toBe("OPEN");
    expect(removed.get("selected")).toBe("11");
  });

  it("validates enum, positive integer, text, and pagination boundaries", () => {
    expect(hasInvalidEnum(new URLSearchParams("status=BAD"), "status", ["OPEN"])).toBe(true);
    expect(hasInvalidPositiveInteger(new URLSearchParams("endpointId=0"), "endpointId")).toBe(true);
    expect(hasInvalidText(new URLSearchParams(`q=${"x".repeat(129)}`), "q", 128)).toBe(true);
    expect(hasInvalidPagination(new URLSearchParams("page=0&size=201"))).toBe(true);
    expect(hasInvalidPagination(new URLSearchParams("page=2&size=100"))).toBe(false);
  });

  it("serializes selection and an allowlisted Event return path", () => {
    const params = new URLSearchParams("status=OPEN&page=2");
    expect(selectedSearch(params, 11)).toContain("selected=11");
    const search = eventDetailSearch(params, { eventId: "event-1", endpointId: 1001, occurredAt: TIMESTAMP });
    const detail = new URLSearchParams(search);
    expect(detail.get("endpointId")).toBe("1001");
    expect(detail.get("occurredAt")).toBe(TIMESTAMP);
    expect(detail.get("returnTo")).toContain("/events?status=OPEN");
    expect(safeReturnPath(detail, "/events")).toContain("selected=event-1");
    expect(safeReturnPath(new URLSearchParams("returnTo=https://example.com"), "/events")).toBe("/events");
  });
});

describe("shared data interaction components", () => {
  it("opens advanced filters as a focus-trapped Drawer and removes applied filters", async () => {
    const user = userEvent.setup();
    const remove = vi.fn();
    renderCommon(<FilterBar advanced={<label>Rule code<input /></label>} appliedFilters={[{ key: "status", label: "Status", value: "Open" }]} hasFilters onClear={() => undefined} onRemoveFilter={remove} primary={<label>Status<select><option>All</option></select></label>} />);
    expect(screen.getByRole("region", { name: "Filters" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "More filters" }));
    expect(screen.getByRole("dialog", { name: "Additional filters" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close additional filters" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Additional filters" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove Status filter" }));
    expect(remove).toHaveBeenCalledWith("status");
  });

  it("provides a caption, keyboard region, sort semantics, URL-safe pagination, and page size", async () => {
    const user = userEvent.setup();
    const sort = vi.fn();
    renderCommon(<><DataTable label="Alert queue"><thead><tr><SortableHeader active direction="desc" label="Detected" onSort={sort} /></tr></thead><tbody><tr><td>row</td></tr></tbody></DataTable><Pagination page={{ items: [], page: 2, size: 50, total: 120 }} /><LocationProbe /></>, "/alerts?status=OPEN&page=2");
    const tableRegion = screen.getByRole("region", { name: "Alert queue table" });
    expect(within(tableRegion).getByText("Alert queue", { selector: "caption" })).toHaveClass("sr-only");
    expect(within(tableRegion).getByRole("columnheader", { name: /Detected/ })).toHaveAttribute("aria-sort", "descending");
    await user.click(within(tableRegion).getByRole("button", { name: /Sort Detected/ }));
    expect(sort).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute("href", "/alerts?status=OPEN");
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute("href", "/alerts?status=OPEN&page=3");
    await user.selectOptions(screen.getByRole("combobox", { name: "Rows per page" }), "25");
    expect(screen.getByTestId("location")).toHaveTextContent("/alerts?status=OPEN&size=25");
  });

  it("distinguishes invalid, pending, stale, forbidden, archive, refreshing, and partial states", () => {
    const forbidden = new ApiError({ status: 403, code: "FORBIDDEN", message: "Forbidden", retryable: false, details: [], requestId: "req_forbidden" });
    const archive = new ApiError({ status: 409, code: "ARCHIVE_NOT_READY", message: "Not ready", retryable: false, details: [], requestId: "req_archive" });
    const stale = new ApiError({ status: 503, code: "SERVICE_UNAVAILABLE", message: "Unavailable", retryable: true, details: [], requestId: "req_stale" });
    renderCommon(<>
      <QueryFeedback error={null} fetching hasData={false} onRetry={() => undefined} pending />
      <QueryFeedback error={null} fetching={false} hasData={false} invalid onRetry={() => undefined} pending={false} />
      <QueryFeedback error={forbidden} fetching={false} hasData={false} onRetry={() => undefined} pending={false} />
      <QueryFeedback error={archive} fetching={false} hasData={false} onRetry={() => undefined} pending={false} />
      <QueryFeedback error={stale} fetching={false} hasData onRetry={() => undefined} pending={false} refetchError />
      <QueryFeedback error={null} fetching hasData onRetry={() => undefined} pending={false} />
      <PartialFailureWarning message="Process evidence is missing." />
    </>);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(screen.getByText("Invalid filters")).toBeInTheDocument();
    expect(screen.getByText("Forbidden")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open archive operations" })).toHaveAttribute("href", "/operations/archives");
    expect(screen.getByText(/Refresh failed/)).toBeInTheDocument();
    expect(screen.getByText("Refreshing data")).toBeInTheDocument();
    expect(screen.getByText("Some evidence is unavailable")).toBeInTheDocument();
  });

  it("names MasterDetail, Inspector, and ChartFrame while keeping a data fallback", () => {
    renderCommon(<MasterDetail label="Investigation workspace" list={<p>Queue</p>} detail={<Inspector title="Selected Alert" description="Evidence context"><p>Inspector body</p></Inspector>} />);
    renderCommon(<ChartFrame title="Detection activity" description="Backend event counts" fallback={<table><tbody><tr><td>10</td></tr></tbody></table>}><svg aria-label="Detection activity chart" role="img" /></ChartFrame>);
    expect(screen.getByRole("region", { name: "Investigation workspace" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Selected Alert" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Detection activity" })).toBeInTheDocument();
    expect(screen.getByText("10")).not.toBeVisible();
  });
});

describe("list pages share the filter, table, state, and URL contract", () => {
  it("keeps Alerts to three primary filters and preserves sort, page, and selection in the URL", async () => {
    const user = userEvent.setup();
    renderPage(<AlertsPage />, "/alerts?status=OPEN");
    const filters = await screen.findByRole("region", { name: "Filters" });
    expect(within(filters).getAllByRole("combobox")).toHaveLength(3);
    await user.click(within(filters).getByRole("button", { name: "More filters" }));
    expect(screen.getByRole("dialog", { name: "Additional filters" })).toHaveTextContent("Rule code");
    await user.keyboard("{Escape}");
    const table = await screen.findByRole("region", { name: "Alert queue table" });
    await user.click(within(table).getByRole("button", { name: /Sort Risk/ }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("sortBy=riskScore&sortOrder=desc"));
    const alertLink = await within(table).findByRole("link", { name: /Suspicious PowerShell/ });
    expect(alertLink.getAttribute("href")).toContain("selected=11");
    expect(screen.getByRole("link", { name: "Next" }).getAttribute("href")).toContain("page=2");
  });

  it("blocks invalid Alerts filters before the API call", async () => {
    renderPage(<AlertsPage />, "/alerts?status=BAD");
    expect(await screen.findByText("Invalid filters")).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes("/api/v1/alerts"))).toBe(false);
  });

  it("offers a compact empty-queue recovery without discarding non-time filters", async () => {
    renderPage(<AlertsPage />, "/alerts?status=RESOLVED&ruleCode=NO_ROWS");
    expect(await screen.findByText(/No alerts found/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Latest 7 days" }));
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("status=RESOLVED");
      expect(screen.getByTestId("location")).toHaveTextContent("ruleCode=NO_ROWS");
      expect(screen.getByTestId("location")).toHaveTextContent("timePreset=LATEST_7D");
    });
  });

  it("uses the same three-primary-plus-advanced contract for Incidents, Endpoints, and Events", async () => {
    const cases = [
      { element: <IncidentsPage />, path: "/incidents", primary: ["Time range", "Status", "Severity"], advanced: "Endpoint ID" },
      { element: <EndpointsPage />, path: "/endpoints", primary: ["Search endpoints", "Status", "Risk level"], advanced: "Endpoint IDs" },
      { element: <EventsPage />, path: "/events", primary: ["Time range", "Endpoint ID", "Event type"], advanced: "process Name" },
    ];
    for (const item of cases) {
      const view = renderPage(item.element, item.path);
      const filters = await screen.findByRole("region", { name: "Filters" });
      for (const label of item.primary) expect(within(filters).getByLabelText(label)).toBeInTheDocument();
      const primaryControls = [
        ...within(filters).queryAllByRole("combobox"),
        ...within(filters).queryAllByRole("textbox"),
      ];
      expect(primaryControls).toHaveLength(3);
      await userEvent.click(within(filters).getByRole("button", { name: "More filters" }));
      expect(screen.getByRole("dialog", { name: "Additional filters" })).toHaveTextContent(item.advanced);
      view.unmount();
    }
  });

  it("keeps Endpoint status semantic while rendering risk as plain numeric text", async () => {
    renderPage(<EndpointsPage />, "/endpoints");
    const table = await screen.findByRole("region", { name: "Endpoint inventory table" });
    const row = within(table).getByRole("link", { name: /WIN-01/ }).closest("tr");
    expect(row).not.toBeNull();
    expect(row?.querySelectorAll(".status-pill")).toHaveLength(1);
    expect(row?.querySelector(".risk-level-text")).toHaveTextContent("High");
    expect(row?.querySelector(".risk-cell strong")).toHaveTextContent("87");
  });

  it("keeps the Endpoints page header title-only", async () => {
    renderPage(<EndpointsPage />, "/endpoints");
    const heading = await screen.findByRole("heading", { level: 1, name: "Endpoints" });
    const header = heading.closest("header");
    expect(header).not.toBeNull();
    expect(header?.querySelector(".eyebrow")).toBeNull();
    expect(header?.querySelector("p")).toBeNull();
  });

  it("keeps Archives at three required filters and distinguishes incomplete from invalid", async () => {
    const view = renderPage(<ArchivesPage />, "/operations/archives");
    const filters = await screen.findByRole("region", { name: "Filters" });
    expect(filters.querySelectorAll("input")).toHaveLength(3);
    expect(filters).toHaveTextContent("Endpoint IDs");
    expect(filters).toHaveTextContent("From");
    expect(filters).toHaveTextContent("To");
    expect(within(filters).queryByRole("button", { name: "More filters" })).not.toBeInTheDocument();
    expect(screen.getByText("Choose an Archive range")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Archive query readiness" })).toHaveTextContent("Maximum 31 days");
    expect(screen.getByRole("region", { name: "Archive query readiness" })).toHaveTextContent("Standard tier · 7 days");
    view.unmount();

    renderPage(<ArchivesPage />, "/operations/archives?endpointIds=bad&from=2026-07-15T00%3A00%3A00Z&to=2026-07-14T00%3A00%3A00Z");
    expect(await screen.findByText("Invalid filters")).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes("/api/v1/archives/restores"))).toBe(false);
  });

  it("preserves Event list context in the detail returnTo query", async () => {
    renderPage(<EventsPage />, "/events?eventType=DNS_QUERY&page=2");
    const table = await screen.findByRole("region", { name: "Event stream table" });
    const link = within(table).getByRole("link", { name: /event-1/ });
    const href = link.getAttribute("href") ?? "";
    expect(href).toContain("endpointId=1001");
    expect(decodeURIComponent(href)).toContain("returnTo=/events?eventType=DNS_QUERY&page=2&selected=event-1");
  });
});

function renderCommon(children: React.ReactNode, entry = "/") {
  return render(<MemoryRouter initialEntries={[entry]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><AuthProvider><LocaleProvider>{children}</LocaleProvider></AuthProvider></QueryClientProvider></MemoryRouter>);
}

function renderPage(element: React.ReactNode, entry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><AuthProvider><LocaleProvider><MemoryRouter initialEntries={[entry]}><Routes><Route path="*" element={<>{element}<LocationProbe /></>} /></Routes></MemoryRouter></LocaleProvider></AuthProvider></QueryClientProvider>);
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

function mockResponse(input: string): Promise<Response> {
  const url = new URL(input, "http://localhost");
  if (url.pathname.endsWith("/users/me")) return Promise.resolve(success(USER));
  const page = Number(url.searchParams.get("page") ?? 1);
  const size = Number(url.searchParams.get("size") ?? 50);
  if (url.pathname.endsWith("/alerts")) return Promise.resolve(success({ items: url.searchParams.get("ruleCode") === "NO_ROWS" ? [] : [alertRow], page, size, total: url.searchParams.get("ruleCode") === "NO_ROWS" ? 0 : 120 }));
  if (url.pathname.endsWith("/incidents")) return Promise.resolve(success({ items: [incidentRow], page, size, total: 1 }));
  if (url.pathname.endsWith("/endpoints")) return Promise.resolve(success({ items: [endpointRow], page, size, total: 1 }));
  if (url.pathname.endsWith("/events")) return Promise.resolve(success({ items: [eventRow], page, size, total: 1 }));
  if (url.pathname.endsWith("/archives/restores")) return Promise.resolve(success({ items: [], page, size, total: 0 }));
  return Promise.reject(new Error(`Unexpected request: ${input}`));
}

function success(data: unknown): Response {
  return new Response(JSON.stringify({ data, meta: { requestId: "req_interaction" } }), { status: 200, headers: { "Content-Type": "application/json" } });
}

const alertRow = { alertId: 11, title: "Suspicious PowerShell", ruleName: "Suspicious PowerShell", ruleCode: "PROC-001", ruleVersion: 2, severity: "HIGH", riskScore: 87, status: "OPEN", endpointId: 1001, agentId: "agent-1", eventId: "event-1", detectedAt: TIMESTAMP, updatedAt: TIMESTAMP };
const incidentRow = { incidentId: 21, endpointId: 1001, title: "Credential access", description: null, severity: "CRITICAL", status: "OPEN", correlationKey: "endpoint:1001", alertCount: 2, windowStartAt: TIMESTAMP, windowEndAt: TIMESTAMP, firstDetectedAt: TIMESTAMP, lastDetectedAt: TIMESTAMP, closedAt: null };
const endpointRow = { endpointId: 1001, agentId: "agent-1", hostname: "WIN-01", osType: "WINDOWS", osVersion: "11", status: "ONLINE", lastSeenAt: TIMESTAMP, isStale: false, risk: { score: 87, level: "HIGH", activeAlertCount: 2, openIncidentCount: 1, highestAlertRiskScore: 87, calculatedAt: TIMESTAMP, riskFactors: [] }, registeredAt: TIMESTAMP };
const eventRow = { eventId: "event-1", batchId: "batch-1", endpointId: 1001, agentId: "agent-1", hostname: "WIN-01", osType: "WINDOWS", ipAddress: "10.0.0.1", eventType: "DNS_QUERY", occurredAt: TIMESTAMP, ingestedAt: TIMESTAMP, processName: "powershell.exe", commandLine: "powershell", remoteDomain: null, remoteIp: null, dnsQuery: "example.com", l7Protocol: null };
