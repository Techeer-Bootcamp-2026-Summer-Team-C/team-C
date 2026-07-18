import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../src/auth/AuthContext";
import type { DashboardSummaryDto, EndpointSummaryDto } from "../src/contracts";
import { LocaleProvider } from "../src/i18n/LocaleContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import type { OverviewDashboardData } from "../src/features/overview/OverviewDashboard";
import {
  OverviewDashboardWorkspace,
  applyDroppedWidget,
  applyGridLayout,
  applyKeyboardWidgetAdjustment,
  tryAddOverviewWidget,
} from "../src/features/overviewLayout/OverviewDashboardWorkspace";
import { OverviewLayoutProvider } from "../src/features/overviewLayout/OverviewLayoutContext";
import { OVERVIEW_GRID_MAX_ROWS, OVERVIEW_WIDGET_DEFINITIONS, overviewWidgetsOverlap, type CustomDashboardWidget } from "../src/features/overviewLayout/overviewLayoutModel";

const USER = { userId: 31, loginId: "analyst", name: "Analyst", role: "ANALYST", status: "ACTIVE", locale: "EN" } as const;

beforeEach(() => {
  sessionStorage.setItem("edr.authSession", JSON.stringify({ token: "dashboard-token", user: USER, expiresAt: Date.now() + 60_000 }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(success(USER)));
  setDesktopEditing(true);
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  document.documentElement.classList.remove("light");
  vi.unstubAllGlobals();
});

describe("custom Overview dashboard", () => {
  it.each(["ADMIN", "ANALYST", "VIEWER"] as const)("enables local dashboard controls for %s", (role) => {
    renderWorkspace(role);
    expect(screen.getByRole("button", { name: "New dashboard" })).toBeEnabled();
  });

  it("always renders the immutable Default Overview even when a custom dashboard is active", () => {
    localStorage.setItem("edr.overviewDashboards.v1.user.31", JSON.stringify({
      version: 1,
      dashboards: [{
        id: "dashboard-custom",
        name: "Custom fixture",
        widgets: [{ uid: "widget-custom", type: "kpi-alerts", x: 0, y: 0, w: 3, h: 2 }],
        createdAt: "2026-07-18T00:00:00Z",
        updatedAt: "2026-07-18T00:00:00Z",
      }],
    }));
    localStorage.setItem("edr.overviewActiveDashboard.v1.user.31", "dashboard-custom");
    const { container } = renderWorkspace(USER.role, "overview");
    expect(screen.queryByRole("region", { name: "Custom dashboard: Custom fixture" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Custom fixture" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete dashboard" })).not.toBeInTheDocument();
    expect(container.querySelectorAll("[data-overview-block]")).toHaveLength(10);
  });

  it("keeps Default immutable and Cancel leaves no dashboard or storage", async () => {
    const user = userEvent.setup();
    const { container } = renderWorkspace();
    expect(container.querySelectorAll("[data-overview-block]")).toHaveLength(0);
    expect(screen.getByRole("region", { name: "Dashboard controls" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit dashboard" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "New dashboard" }));
    expect(screen.getByRole("heading", { name: "Build a new dashboard" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open dashboard settings" }));
    expect(screen.getByRole("combobox", { name: "Dashboard" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "New dashboard" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Close settings" }));
    expect(screen.getByRole("button", { name: "Save dashboard" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Add Total alerts" }));
    await user.type(screen.getByRole("textbox", { name: "Dashboard name" }), "Priority investigation");
    expect(screen.getByRole("button", { name: "Save dashboard" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(localStorage.getItem("edr.overviewDashboards.v1.user.31")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Open dashboard settings" }));
    expect(screen.getByRole("combobox", { name: "Dashboard" })).toHaveValue("default");
    expect(container.querySelectorAll("[data-overview-block]")).toHaveLength(0);
    expect(screen.getByRole("region", { name: "Dashboard controls" })).toBeInTheDocument();
  });

  it("creates duplicate widget instances, edits them through Save, and deletes to Default", async () => {
    const user = userEvent.setup();
    const { container } = renderWorkspace();
    await user.click(screen.getByRole("button", { name: "New dashboard" }));
    await user.click(screen.getByRole("button", { name: "Add Total alerts" }));
    await user.click(screen.getByRole("button", { name: "Add Total alerts" }));
    await user.type(screen.getByRole("textbox", { name: "Dashboard name" }), "Priority investigation");
    await user.click(screen.getByRole("button", { name: "Save dashboard" }));

    expect(screen.getByRole("region", { name: "Custom dashboard: Priority investigation" })).toBeInTheDocument();
    expect(container.querySelectorAll('[data-widget-type="kpi-alerts"]')).toHaveLength(2);
    expect(container.querySelectorAll(".overview-signal-ribbon")).toHaveLength(1);
    const stored = JSON.parse(localStorage.getItem("edr.overviewDashboards.v1.user.31") ?? "{}");
    expect(stored.dashboards[0].widgets).toHaveLength(2);
    expect(new Set(stored.dashboards[0].widgets.map((widget: CustomDashboardWidget) => widget.uid)).size).toBe(2);

    await user.click(screen.getByRole("button", { name: "Open dashboard settings" }));
    await user.click(screen.getByRole("button", { name: "Edit dashboard" }));
    await user.click(screen.getByRole("button", { name: "Open dashboard settings" }));
    expect(screen.getByRole("combobox", { name: "Dashboard" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "New dashboard" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Edit dashboard" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete dashboard" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Close settings" }));
    const name = screen.getByRole("textbox", { name: "Dashboard name" });
    await user.clear(name);
    await user.type(name, "Triage focus");
    await user.click(screen.getAllByRole("button", { name: "Remove Total alerts" })[0]!);
    await user.click(screen.getByRole("button", { name: "Save dashboard" }));
    expect(screen.getByRole("region", { name: "Custom dashboard: Triage focus" })).toBeInTheDocument();
    expect(container.querySelectorAll('[data-widget-type="kpi-alerts"]')).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Open dashboard settings" }));
    await user.click(screen.getByRole("button", { name: "Delete dashboard" }));
    const dialog = screen.getByRole("dialog", { name: "Delete custom dashboard" });
    await user.click(within(dialog).getByRole("button", { name: "Delete dashboard" }));
    await user.click(screen.getByRole("button", { name: "Open dashboard settings" }));
    expect(screen.getByRole("combobox", { name: "Dashboard" })).toHaveValue("default");
    expect(container.querySelectorAll("[data-overview-block]")).toHaveLength(0);
    expect(screen.getByRole("region", { name: "Dashboard controls" })).toBeInTheDocument();
  });

  it("disables custom dashboard editing below 1280px without removing saved content", async () => {
    setDesktopEditing(false);
    renderWorkspace();
    expect(screen.getByRole("button", { name: "New dashboard" })).toBeDisabled();
    expect(screen.getByText("Custom dashboard editing is available at 1280px and wider.")).toBeInTheDocument();
  });

  it("freezes an open builder when the viewport crosses below 1280px", async () => {
    const editing = installDesktopEditing(true);
    const user = userEvent.setup();
    const { container } = renderWorkspace();
    await user.click(screen.getByRole("button", { name: "New dashboard" }));
    await user.click(screen.getByRole("button", { name: "Add Total alerts" }));
    await user.type(screen.getByRole("textbox", { name: "Dashboard name" }), "Breakpoint guard");
    expect(screen.getByRole("button", { name: "Save dashboard" })).toBeEnabled();

    act(() => editing.set(false));

    expect(screen.getByRole("textbox", { name: "Dashboard name" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add Total alerts" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save dashboard" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Move Total alerts\./ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Remove Total alerts" })).not.toBeInTheDocument();
    expect(container.querySelector('[data-dashboard-editing="disabled"]')).toBeInTheDocument();
    expect(localStorage.getItem("edr.overviewDashboards.v1.user.31")).toBeNull();
  });

  it("maps drag and resize stop geometry without changing widget identity", () => {
    const widgets: CustomDashboardWidget[] = [
      { uid: "widget-1", type: "kpi-alerts", x: 0, y: 0, w: 3, h: 2 },
      { uid: "widget-2", type: "kpi-alerts", x: 3, y: 0, w: 3, h: 2 },
    ];
    const updated = applyGridLayout(widgets, [
      { i: "widget-1", x: 6, y: 4, w: 4, h: 3 },
      { i: "widget-2", x: 0, y: 0, w: 3, h: 2 },
    ]);
    expect(updated[0]).toEqual({ uid: "widget-1", type: "kpi-alerts", x: 6, y: 4, w: 4, h: 3 });
    expect(updated[1]).toEqual({ uid: "widget-2", type: "kpi-alerts", x: 0, y: 0, w: 3, h: 2 });

    const source = readFileSync("src/features/overviewLayout/OverviewDashboardWorkspace.tsx", "utf8");
    expect(source).toContain("onDragStop={commitLayout}");
    expect(source).toContain("onResizeStop={commitLayout}");
    expect(source).toContain("getCompactor(null, false, true)");
    expect(source).not.toContain("onDrag={commitLayout}");
    expect(source).not.toContain("onResize={commitLayout}");
  });

  it("preserves existing geometry and places only the dropped widget", () => {
    const widgets: CustomDashboardWidget[] = [
      { uid: "widget-1", type: "kpi-alerts", x: 0, y: 0, w: 3, h: 2 },
      { uid: "widget-2", type: "kpi-alerts", x: 0, y: 2, w: 3, h: 2 },
    ];
    const updated = applyDroppedWidget(widgets, "detection-activity", { x: 0, y: 0, w: 8, h: 7 });

    expect(updated.slice(0, 2)).toEqual(widgets);
    expect(updated[2]).toMatchObject({ type: "detection-activity", x: 3, y: 0, w: 8, h: 10 });
    expect(updated[2]?.uid).not.toBe("__dropping-elem__");
  });

  it("fills available width before adding another row", () => {
    const first = tryAddOverviewWidget([], "highest-risk-endpoints");
    const second = tryAddOverviewWidget(first, "highest-risk-endpoints");

    expect(first[0]).toMatchObject({ x: 0, y: 0, w: 6, h: 7 });
    expect(second[1]).toMatchObject({ x: 6, y: 0, w: 6, h: 7 });
  });

  it("keeps saved widgets static and persists keyboard geometry only after explicit Save", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await user.click(screen.getByRole("button", { name: "New dashboard" }));
    await user.click(screen.getByRole("button", { name: "Add Total alerts" }));
    await user.type(screen.getByRole("textbox", { name: "Dashboard name" }), "Keyboard layout");
    await user.click(screen.getByRole("button", { name: "Save dashboard" }));

    expect(screen.getByRole("button", { name: /^Move Total alerts\./ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Open dashboard settings" }));
    await user.click(screen.getByRole("button", { name: "Edit dashboard" }));
    const handle = screen.getByRole("button", { name: /^Move Total alerts\./ });
    const gridItem = handle.closest<HTMLElement>(".react-grid-item");
    expect(gridItem).not.toBeNull();
    expect(handle).toHaveAttribute("aria-keyshortcuts", expect.stringContaining("Shift+ArrowRight"));
    handle.focus();
    await user.keyboard("{ArrowRight}{ArrowDown}{Shift>}{ArrowRight}{ArrowDown}{/Shift}");

    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem("edr.overviewDashboards.v1.user.31") ?? "{}");
      expect(stored.dashboards[0].widgets[0]).toMatchObject({ x: 0, y: 0, w: 3, h: 2 });
      expect(gridItem?.style.transform).toMatch(/, ?56px\)$/);
    });
    expect(screen.getByRole("button", { name: /Total alerts: column 2, row 2, width 4, height 3/ })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Save dashboard" }));
    const stored = JSON.parse(localStorage.getItem("edr.overviewDashboards.v1.user.31") ?? "{}");
    expect(stored.dashboards[0].widgets[0]).toMatchObject({ x: 1, y: 1, w: 4, h: 3 });
  });

  it("clamps invalid RGL geometry and repairs overlap before it reaches the draft", () => {
    const widgets: CustomDashboardWidget[] = [
      { uid: "widget-1", type: "kpi-alerts", x: 0, y: 0, w: 3, h: 2 },
      { uid: "widget-2", type: "kpi-open-incidents", x: 3, y: 0, w: 3, h: 2 },
    ];
    const updated = applyGridLayout(widgets, [
      { i: "widget-1", x: -30, y: -5, w: 99, h: 0 },
      { i: "widget-2", x: 0, y: 0, w: 3, h: 2 },
    ]);

    expect(updated[0]).toMatchObject({ x: 0, y: 0, w: 6, h: 2 });
    expect(updated[1]!.x + updated[1]!.w).toBeLessThanOrEqual(12);
    expect(updated[1]!.y + updated[1]!.h).toBeLessThanOrEqual(OVERVIEW_GRID_MAX_ROWS);
    expect(overviewWidgetsOverlap(updated[0]!, updated[1]!)).toBe(false);
  });

  it("rejects keyboard adjustments that cross a grid boundary or another widget", () => {
    const widgets: CustomDashboardWidget[] = [
      { uid: "widget-1", type: "kpi-alerts", x: 0, y: 0, w: 3, h: 2 },
      { uid: "widget-2", type: "kpi-alerts", x: 4, y: 0, w: 3, h: 2 },
    ];
    const moved = applyKeyboardWidgetAdjustment(widgets, "widget-1", "ArrowRight", false);
    expect(moved[0]).toMatchObject({ x: 1, y: 0, w: 3, h: 2 });
    expect(applyKeyboardWidgetAdjustment(moved, "widget-1", "ArrowRight", false)).toBe(moved);

    const resized = applyKeyboardWidgetAdjustment(widgets, "widget-1", "ArrowRight", true);
    expect(resized[0]).toMatchObject({ x: 0, y: 0, w: 4, h: 2 });
    expect(applyKeyboardWidgetAdjustment(resized, "widget-1", "ArrowRight", true)).toBe(resized);
    expect(applyKeyboardWidgetAdjustment(widgets, "widget-1", "ArrowLeft", false)).toBe(widgets);
  });

  it("rejects only the widget size that cannot fit in the remaining grid space", () => {
    let widgets: CustomDashboardWidget[] = [];
    for (let index = 0; index < 25; index += 1) {
      const next = tryAddOverviewWidget(widgets, "detection-activity");
      expect(next).not.toBe(widgets);
      widgets = next;
    }

    expect(tryAddOverviewWidget(widgets, "detection-activity")).toBe(widgets);
    expect(widgets).toHaveLength(25);
    widgets.forEach((widget, index) => {
      expect(widget.y + widget.h).toBeLessThanOrEqual(OVERVIEW_GRID_MAX_ROWS);
      expect(widgets.slice(index + 1).every((candidate) => !overviewWidgetsOverlap(widget, candidate))).toBe(true);
    });

    const withSmallerWidget = tryAddOverviewWidget(widgets, "alert-severity");
    expect(withSmallerWidget).toHaveLength(26);
    expect(withSmallerWidget.at(-1)).toMatchObject({ type: "alert-severity", x: 8, y: 0, w: 4, h: 7 });
  });

  it("uses content-safe widget geometry without nested body scrolling", () => {
    const definitions = Object.fromEntries(OVERVIEW_WIDGET_DEFINITIONS.map((definition) => [definition.type, definition]));
    expect(definitions["edr-state"]).toMatchObject({ defaultW: 12, defaultH: 4, minW: 12, minH: 4 });
    expect(definitions["detection-activity"]).toMatchObject({ defaultH: 10, minH: 10 });
    expect(definitions["alert-severity"]).toMatchObject({ defaultW: 4, defaultH: 7, minW: 4, minH: 7 });
    expect(definitions["highest-risk-endpoints"]).toMatchObject({ defaultW: 6, defaultH: 7, minW: 6, minH: 7 });
    expect(definitions["incident-queue"]).toMatchObject({ defaultW: 6, defaultH: 7, minW: 6, minH: 7 });

    const css = readFileSync("src/styles/pages/overview-layout.css", "utf8");
    const widgetBodyRule = css.match(/\.custom-dashboard-widget-body\s*\{[^}]+\}/)?.[0] ?? "";
    expect(widgetBodyRule).toContain("container: dashboard-widget-body / inline-size");
    expect(widgetBodyRule).toContain("overflow: hidden");
    expect(widgetBodyRule).not.toContain("overflow: auto");
  });
});

function renderWorkspace(role: "ADMIN" | "ANALYST" | "VIEWER" = USER.role, mode: "overview" | "manage" = "manage") {
  const user = { ...USER, role };
  sessionStorage.setItem("edr.authSession", JSON.stringify({ token: "dashboard-token", user, expiresAt: Date.now() + 60_000 }));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><MemoryRouter>
    <OverviewLayoutProvider userId={user.userId}>
      <WorkspaceHarness mode={mode} />
    </OverviewLayoutProvider>
  </MemoryRouter></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);
}

function WorkspaceHarness({ mode }: { mode: "overview" | "manage" }) {
  const [settingsOpen, setSettingsOpen] = useState(mode === "manage");
  return <>
    <button onClick={() => setSettingsOpen(true)} type="button">Open dashboard settings</button>
    <OverviewDashboardWorkspace data={overviewData()} mode={mode} onSettingsClose={() => setSettingsOpen(false)} settingsOpen={settingsOpen} />
  </>;
}

function setDesktopEditing(matches: boolean): void {
  vi.stubGlobal("matchMedia", vi.fn().mockImplementation((query: string) => ({
    matches: query === "(min-width: 1280px)" ? matches : false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })));
}

function installDesktopEditing(initialMatches: boolean): { set: (matches: boolean) => void } {
  let matches = initialMatches;
  const listeners = new Set<() => void>();
  vi.stubGlobal("matchMedia", vi.fn().mockImplementation((query: string) => ({
    get matches() { return query === "(min-width: 1280px)" ? matches : false; },
    media: query,
    onchange: null,
    addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
    addListener: (listener: () => void) => listeners.add(listener),
    removeListener: (listener: () => void) => listeners.delete(listener),
    dispatchEvent: vi.fn(),
  })));
  return {
    set(nextMatches: boolean) {
      matches = nextMatches;
      listeners.forEach((listener) => listener());
    },
  };
}

function overviewData(): OverviewDashboardData {
  return {
    dashboard: {
      edrState: { status: "GREEN", score: 10, threatLevel: { status: "GREEN", score: 10, reasonCodes: [] }, collectionHealth: { status: "GREEN", score: 0, reasonCodes: [] }, reasonCodes: [], calculatedAt: "2026-07-17T00:00:00Z" },
      alerts: { totalCount: 3, bySeverity: [{ severity: "CRITICAL", count: 1 }], timeSeries: [] },
      events: { totalCount: 8, timeSeries: [] },
      incidents: { openCount: 1, timeSeries: [] },
    } as unknown as DashboardSummaryDto,
    endpoints: { totalCount: 2, onlineCount: 2, risk: { highRiskEndpointCount: 1 } } as unknown as EndpointSummaryDto,
    topEndpoints: [],
    incidentQueue: [],
    selectedEndpointId: undefined,
    timeRange: { timePreset: "LATEST_24H" },
  };
}

function success(data: unknown): Response {
  return new Response(JSON.stringify({ data, meta: { requestId: "req_custom_dashboard" } }), { status: 200, headers: { "Content-Type": "application/json" } });
}
