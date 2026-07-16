import { describe, expect, it } from "vitest";
import {
  applyDesktopGridLayout,
  createDefaultOverviewLayout,
  layoutsEqual,
  mobileGridLayout,
  moveWidgetInOrder,
  normalizeOverviewLayout,
  orderedVisibleWidgets,
  resolveOverviewLayout,
  resizeWidgetByStep,
  restoreWidgetAtGridPosition,
  setWidgetHidden,
  tabletGridLayout,
  widgetDisplayMode,
} from "../src/features/dashboardLayout";
import { dashboardLayoutV1Fixture } from "./dashboard-layout-v1.fixture";

describe("overview dashboard layout", () => {
  it("migrates the static v1 fixture to the approved v2 registry without losing supported choices", () => {
    const resolved = resolveOverviewLayout(dashboardLayoutV1Fixture.data.layoutVersion, dashboardLayoutV1Fixture.data.widgets);
    const normalized = resolved.widgets;

    expect(dashboardLayoutV1Fixture.data.layoutVersion).toBe(1);
    expect(dashboardLayoutV1Fixture.data.revision).toBe(7);
    expect(resolved.migrationRequired).toBe(true);
    expect(normalized).toHaveLength(10);
    expect(normalized.find((item) => item.id === "detection-activity")).toMatchObject({ w: 12, h: 6 });
    expect(normalized.some((item) => item.id === "event-volume")).toBe(false);
    expect(normalized.some((item) => item.id === "kpi-high-risk-endpoints")).toBe(true);
  });

  it("creates a complete non-overlapping default layout", () => {
    const layout = createDefaultOverviewLayout();
    expect(layout).toHaveLength(10);
    expect(new Set(layout.map((item) => item.id)).size).toBe(10);
    expect(layout.every((item) => item.x >= 0 && item.x + item.w <= 12)).toBe(true);
    for (const [index, item] of layout.entries()) {
      for (const other of layout.slice(0, index)) expect(overlaps(item, other)).toBe(false);
    }
  });

  it("merges partial layouts, adds new widgets, and ignores removed and duplicate ids", () => {
    const merged = normalizeOverviewLayout([
      { id: "detection-activity", x: 4, y: 2, w: 8, h: 5, hidden: false },
      { id: "detection-activity", x: 0, y: 99, w: 6, h: 4, hidden: true },
      { id: "kpi-alerts", x: 0, y: 2, w: 2, h: 2, hidden: "true" },
      { id: "removed-widget", x: 0, y: 0, w: 1, h: 1, hidden: false },
    ]);
    expect(merged).toHaveLength(10);
    expect(merged.filter((item) => item.id === "detection-activity")).toHaveLength(1);
    expect(merged.some((item) => item.id === "removed-widget")).toBe(false);
    expect(merged.find((item) => item.id === "kpi-alerts")?.hidden).toBe(false);
  });

  it("normalizes invalid coordinates and widget-specific size limits", () => {
    const normalized = normalizeOverviewLayout([
      { id: "detection-activity", x: 99, y: -20, w: 99, h: 1, hidden: false },
      { id: "kpi-alerts", x: -4, y: 0, w: 0, h: 100, hidden: false },
    ]);
    expect(normalized.find((item) => item.id === "detection-activity")).toMatchObject({ x: 0, w: 12, h: 4 });
    expect(normalized.find((item) => item.id === "kpi-alerts")).toMatchObject({ x: 0, w: 1, h: 3 });
  });

  it("hides, restores, moves, and resizes widgets with pure operations", () => {
    const defaults = createDefaultOverviewLayout();
    const hidden = setWidgetHidden(defaults, "kpi-alerts", true);
    expect(hidden.find((item) => item.id === "kpi-alerts")?.hidden).toBe(true);
    const restored = setWidgetHidden(hidden, "kpi-alerts", false);
    expect(restored.find((item) => item.id === "kpi-alerts")?.hidden).toBe(false);

    const moved = moveWidgetInOrder(restored, "kpi-alerts", -1);
    expect(orderedVisibleWidgets(moved)[0]?.id).toBe("kpi-alerts");
    const narrower = resizeWidgetByStep(moved, "kpi-alerts", "width", -1);
    expect(narrower.find((item) => item.id === "kpi-alerts")?.w).toBe(2);
    expect(layoutsEqual(createDefaultOverviewLayout(), defaults)).toBe(true);
  });

  it("derives compact, standard, and expanded modes from grid dimensions", () => {
    const kpi = createDefaultOverviewLayout().find((item) => item.id === "kpi-alerts");
    if (!kpi) throw new Error("missing KPI");
    expect(widgetDisplayMode(kpi)).toBe("standard");
    expect(widgetDisplayMode({ ...kpi, w: 1 })).toBe("compact");
    expect(widgetDisplayMode({ ...kpi, w: 4, h: 3 })).toBe("expanded");
  });

  it("keeps saved order while deriving the 6-column tablet layout", () => {
    const desktop = createDefaultOverviewLayout();
    const tablet = tabletGridLayout(desktop);
    const expectedOrder = orderedVisibleWidgets(desktop).map((item) => item.id);
    expect([...tablet].sort(positionSort).map((item) => item.i)).toEqual(expectedOrder);
    expect(tablet.every((item) => item.x >= 0 && item.x + item.w <= 6)).toBe(true);
    expect([...rowWidths(tablet).values()].every((width) => width === 6)).toBe(true);
  });

  it("removes horizontal gaps from uneven saved rows in the tablet layout", () => {
    const uneven = normalizeOverviewLayout(createDefaultOverviewLayout().map((item) => {
      if (item.id === "kpi-alerts") return { ...item, x: 2, w: 2 };
      if (item.id === "kpi-open-incidents") return { ...item, x: 4, w: 2 };
      if (item.id === "kpi-high-risk-endpoints") return { ...item, x: 6, w: 3 };
      if (item.id === "kpi-event-failures") return { ...item, x: 9, w: 2 };
      if (item.id === "highest-risk-endpoints") return { ...item, w: 4 };
      if (item.id === "incident-queue") return { ...item, x: 6, w: 6 };
      return item;
    }));
    const tablet = tabletGridLayout(uneven);

    expect([...rowWidths(tablet).values()].every((width) => width === 6)).toBe(true);
    expect(tablet.filter((item) => item.i.startsWith("kpi-")).map((item) => item.w)).toEqual([3, 3, 3, 3]);
  });

  it("uses a readable single-column layout below the tablet breakpoint", () => {
    const desktop = createDefaultOverviewLayout();
    const mobile = mobileGridLayout(desktop);
    expect(mobile.map((item) => item.i)).toEqual(orderedVisibleWidgets(desktop).map((item) => item.id));
    expect(mobile.every((item) => item.x === 0 && item.w === 1 && item.isDraggable === false)).toBe(true);
    expect(mobile.slice(1).every((item, index) => {
      const previous = mobile[index];
      return previous ? item.y >= previous.y + previous.h : false;
    })).toBe(true);
  });

  it("restores a hidden widget at its dropped grid position", () => {
    const hidden = setWidgetHidden(createDefaultOverviewLayout(), "kpi-alerts", true);
    const restored = restoreWidgetAtGridPosition(hidden, "kpi-alerts", { x: 8, y: 40, w: 3, h: 2 });
    expect(restored.find((item) => item.id === "kpi-alerts")).toMatchObject({ hidden: false, x: 8, w: 3, h: 2 });
  });

  it("applies collision-resolved grid output without losing hidden widgets", () => {
    const current = setWidgetHidden(createDefaultOverviewLayout(), "kpi-alerts", true);
    const visible = current.filter((item) => !item.hidden).map((item) => ({
      i: item.id, x: item.x, y: item.y, w: item.w, h: item.h,
    }));
    const changed = applyDesktopGridLayout(current, visible);
    expect(changed).toHaveLength(10);
    expect(changed.find((item) => item.id === "kpi-alerts")?.hidden).toBe(true);
  });
});

function overlaps(first: { x: number; y: number; w: number; h: number }, second: { x: number; y: number; w: number; h: number }): boolean {
  return !(first.x + first.w <= second.x || second.x + second.w <= first.x
    || first.y + first.h <= second.y || second.y + second.h <= first.y);
}

function positionSort(first: { x: number; y: number }, second: { x: number; y: number }): number {
  return first.y - second.y || first.x - second.x;
}

function rowWidths(layout: readonly { y: number; w: number }[]): Map<number, number> {
  const widths = new Map<number, number>();
  for (const item of layout) widths.set(item.y, (widths.get(item.y) ?? 0) + item.w);
  return widths;
}
