import { describe, expect, it } from "vitest";
import {
  applyDesktopGridLayout,
  createDefaultOverviewLayout,
  layoutsEqual,
  moveWidgetInOrder,
  normalizeOverviewLayout,
  orderedVisibleWidgets,
  resizeWidgetByStep,
  restoreWidgetAtGridPosition,
  setWidgetHidden,
  tabletGridLayout,
  widgetDisplayMode,
} from "../src/features/dashboardLayout";

describe("overview dashboard layout", () => {
  it("creates a complete non-overlapping default layout", () => {
    const layout = createDefaultOverviewLayout();
    expect(layout).toHaveLength(23);
    expect(new Set(layout.map((item) => item.id)).size).toBe(23);
    expect(layout.every((item) => item.x >= 0 && item.x + item.w <= 12)).toBe(true);
    for (const [index, item] of layout.entries()) {
      for (const other of layout.slice(0, index)) expect(overlaps(item, other)).toBe(false);
    }
  });

  it("merges partial layouts, adds new widgets, and ignores removed and duplicate ids", () => {
    const merged = normalizeOverviewLayout([
      { id: "event-volume", x: 4, y: 2, w: 8, h: 5, hidden: false },
      { id: "event-volume", x: 0, y: 99, w: 6, h: 4, hidden: true },
      { id: "kpi-events", x: 0, y: 2, w: 2, h: 2, hidden: "true" },
      { id: "removed-widget", x: 0, y: 0, w: 1, h: 1, hidden: false },
    ]);
    expect(merged).toHaveLength(23);
    expect(merged.filter((item) => item.id === "event-volume")).toHaveLength(1);
    expect(merged.some((item) => item.id === "removed-widget")).toBe(false);
    expect(merged.some((item) => item.id === "kpi-events")).toBe(true);
    expect(merged.find((item) => item.id === "kpi-events")?.hidden).toBe(false);
  });

  it("normalizes invalid coordinates and widget-specific size limits", () => {
    const normalized = normalizeOverviewLayout([
      { id: "event-volume", x: 99, y: -20, w: 99, h: 1, hidden: false },
      { id: "kpi-events", x: -4, y: 0, w: 0, h: 100, hidden: false },
    ]);
    expect(normalized.find((item) => item.id === "event-volume")).toMatchObject({ x: 0, w: 12, h: 4 });
    expect(normalized.find((item) => item.id === "kpi-events")).toMatchObject({ x: 0, w: 1, h: 3 });
  });

  it("hides, restores, resets, moves, and resizes widgets with pure operations", () => {
    const defaults = createDefaultOverviewLayout();
    const hidden = setWidgetHidden(defaults, "kpi-events", true);
    expect(hidden.find((item) => item.id === "kpi-events")?.hidden).toBe(true);
    const restored = setWidgetHidden(hidden, "kpi-events", false);
    expect(restored.find((item) => item.id === "kpi-events")?.hidden).toBe(false);

    const moved = moveWidgetInOrder(restored, "kpi-alerts", -1);
    expect(orderedVisibleWidgets(moved)[1]?.id).toBe("kpi-alerts");
    const narrower = resizeWidgetByStep(moved, "kpi-alerts", "width", -1);
    expect(narrower.find((item) => item.id === "kpi-alerts")?.w).toBe(1);
    expect(layoutsEqual(createDefaultOverviewLayout(), defaults)).toBe(true);
  });

  it("derives compact, standard, and expanded modes from grid dimensions", () => {
    const kpi = createDefaultOverviewLayout().find((item) => item.id === "kpi-events");
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
  });

  it("restores a hidden widget at its dropped grid position", () => {
    const hidden = setWidgetHidden(createDefaultOverviewLayout(), "kpi-events", true);
    const restored = restoreWidgetAtGridPosition(hidden, "kpi-events", { x: 8, y: 40, w: 3, h: 2 });
    expect(restored.find((item) => item.id === "kpi-events")).toMatchObject({
      hidden: false,
      x: 8,
      w: 3,
      h: 2,
    });
  });

  it("applies collision-resolved grid output without losing hidden widgets", () => {
    const current = setWidgetHidden(createDefaultOverviewLayout(), "kpi-events", true);
    const visible = current.filter((item) => !item.hidden).map((item) => ({
      i: item.id,
      x: item.x,
      y: item.y,
      w: item.w,
      h: item.h,
    }));
    const changed = applyDesktopGridLayout(current, visible);
    expect(changed).toHaveLength(23);
    expect(changed.find((item) => item.id === "kpi-events")?.hidden).toBe(true);
  });
});

function overlaps(first: { x: number; y: number; w: number; h: number }, second: { x: number; y: number; w: number; h: number }): boolean {
  return !(first.x + first.w <= second.x || second.x + second.w <= first.x
    || first.y + first.h <= second.y || second.y + second.h <= first.y);
}

function positionSort(first: { x: number; y: number }, second: { x: number; y: number }): number {
  return first.y - second.y || first.x - second.x;
}
