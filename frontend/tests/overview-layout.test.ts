import { describe, expect, it } from "vitest";
import {
  activeDashboardStorageKey,
  dashboardsStorageKey,
  normalizeOverviewDashboardStore,
  parseOverviewDashboardStore,
  readOverviewLayoutState,
  writeOverviewLayoutState,
} from "../src/features/overviewLayout/overviewLayoutStorage";
import { OVERVIEW_WIDGET_DEFINITIONS } from "../src/features/overviewLayout/overviewLayoutModel";

describe("Overview dashboard storage model", () => {
  it("separates storage by numeric userId", () => {
    expect(dashboardsStorageKey(7)).toBe("edr.overviewDashboards.v1.user.7");
    expect(activeDashboardStorageKey(8)).toBe("edr.overviewActiveDashboard.v1.user.8");
    expect(dashboardsStorageKey(7)).not.toBe(dashboardsStorageKey(8));
  });

  it("falls back for malformed JSON and unsupported versions", () => {
    expect(parseOverviewDashboardStore("{broken").dashboards).toEqual([]);
    expect(normalizeOverviewDashboardStore({ version: 2, dashboards: [] }).dashboards).toEqual([]);
  });

  it("drops unknown widgets, duplicate UIDs, and duplicate types while clamping geometry", () => {
    const store = normalizeOverviewDashboardStore({
      version: 1,
      dashboards: [{
        id: "dash-1",
        name: "  Investigation  ",
        createdAt: "invalid",
        updatedAt: "2026-07-17T00:00:00Z",
        widgets: [
          { uid: "widget-a", type: "kpi-alerts", x: -9, y: -1, w: 99, h: 0 },
          { uid: "widget-b", type: "kpi-alerts", x: 11, y: 999, w: 3, h: 2 },
          { uid: "widget-b", type: "alert-severity", x: 0, y: 0, w: 4, h: 7 },
          { uid: "unknown", type: "made-up", x: 0, y: 0, w: 4, h: 4 },
        ],
      }],
    });

    expect(store.dashboards).toHaveLength(1);
    expect(store.dashboards[0]?.name).toBe("Investigation");
    expect(store.dashboards[0]?.widgets.map((widget) => widget.type)).toEqual(["kpi-alerts", "alert-severity"]);
    expect(store.dashboards[0]?.widgets.map((widget) => widget.uid)).toEqual(["widget-a", "widget-b"]);
    expect(store.dashboards[0]?.widgets[0]).toMatchObject({ x: 0, y: 0, w: 6, h: 2 });
    expect(store.dashboards[0]?.widgets[1]).toMatchObject({ x: 6, y: 0, w: 4, h: 7 });
    expect(store.dashboards[0]?.createdAt).toBe(new Date(0).toISOString());
  });

  it("restores only an active dashboard that belongs to the same user", () => {
    const storage = new MemoryStorage();
    const state = {
      dashboards: [{ id: "dash-a", name: "A", widgets: [{ uid: "one", type: "kpi-alerts" as const, x: 0, y: 0, w: 3, h: 2 }], createdAt: "2026-07-17T00:00:00.000Z", updatedAt: "2026-07-17T00:00:00.000Z" }],
      activeDashboardId: "dash-a",
    };
    writeOverviewLayoutState(1, state, storage);
    expect(readOverviewLayoutState(1, storage).activeDashboardId).toBe("dash-a");
    expect(readOverviewLayoutState(2, storage)).toEqual({ dashboards: [], activeDashboardId: "default" });
  });

  it("keeps an in-memory fallback when storage throws", () => {
    const storage = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(readOverviewLayoutState(1, storage)).toEqual({ dashboards: [], activeDashboardId: "default" });
    expect(() => writeOverviewLayoutState(1, { dashboards: [], activeDashboardId: "default" }, storage)).not.toThrow();
  });

  it("keeps all valid dashboards and unique widget types during normalization", () => {
    const dashboards = Array.from({ length: 25 }, (_, dashboardIndex) => ({
      id: `dash-${dashboardIndex}`,
      name: `Dashboard ${dashboardIndex}`,
      createdAt: "2026-07-17T00:00:00.000Z",
      updatedAt: "2026-07-17T00:00:00.000Z",
      widgets: (dashboardIndex === 0 ? OVERVIEW_WIDGET_DEFINITIONS : OVERVIEW_WIDGET_DEFINITIONS.slice(0, 1)).map((definition, widgetIndex) => ({
        uid: `widget-${dashboardIndex}-${widgetIndex}`,
        type: definition.type,
        x: 0,
        y: 0,
        w: definition.defaultW,
        h: definition.defaultH,
      })),
    }));

    const store = normalizeOverviewDashboardStore({ version: 1, dashboards });
    expect(store.dashboards).toHaveLength(25);
    expect(store.dashboards[0]?.widgets).toHaveLength(OVERVIEW_WIDGET_DEFINITIONS.length);
    expect(store.dashboards[24]?.id).toBe("dash-24");
  });

  it("repositions overlapping stored widgets into available in-bounds cells", () => {
    const store = normalizeOverviewDashboardStore({
      version: 1,
      dashboards: [{
        id: "dash-overlap",
        name: "Recovered",
        createdAt: "2026-07-17T00:00:00.000Z",
        updatedAt: "2026-07-17T00:00:00.000Z",
        widgets: [
          { uid: "widget-1", type: "kpi-alerts", x: 0, y: 0, w: 3, h: 2 },
          { uid: "widget-2", type: "kpi-open-incidents", x: 0, y: 0, w: 3, h: 2 },
        ],
      }],
    });

    expect(store.dashboards[0]?.widgets).toEqual([
      { uid: "widget-1", type: "kpi-alerts", x: 0, y: 0, w: 3, h: 2 },
      { uid: "widget-2", type: "kpi-open-incidents", x: 3, y: 0, w: 3, h: 2 },
    ]);
  });

  it("bounds normalization work for large duplicate-type arrays", () => {
    const widgets = Array.from({ length: 5_000 }, (_, index) => {
      const definition = OVERVIEW_WIDGET_DEFINITIONS[index % OVERVIEW_WIDGET_DEFINITIONS.length]!;
      return {
        uid: `widget-${index}`,
        type: definition.type,
        x: 0,
        y: 0,
        w: definition.defaultW,
        h: definition.defaultH,
      };
    });
    const startedAt = performance.now();
    const store = normalizeOverviewDashboardStore({
      version: 1,
      dashboards: [{
        id: "dash-over-capacity",
        name: "Bounded",
        createdAt: "2026-07-17T00:00:00.000Z",
        updatedAt: "2026-07-17T00:00:00.000Z",
        widgets,
      }],
    });

    expect(store.dashboards[0]?.widgets).toHaveLength(OVERVIEW_WIDGET_DEFINITIONS.length);
    expect(performance.now() - startedAt).toBeLessThan(1_000);
  });

  it("falls back when the localStorage property getter throws", () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, "localStorage");
    expect(descriptor).toBeDefined();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get: () => { throw new DOMException("blocked", "SecurityError"); },
    });

    try {
      expect(readOverviewLayoutState(1)).toEqual({ dashboards: [], activeDashboardId: "default" });
      expect(() => writeOverviewLayoutState(1, { dashboards: [], activeDashboardId: "default" })).not.toThrow();
    } finally {
      if (descriptor) Object.defineProperty(window, "localStorage", descriptor);
    }
  });
});

class MemoryStorage {
  private readonly values = new Map<string, string>();
  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void { this.values.set(key, value); }
}
