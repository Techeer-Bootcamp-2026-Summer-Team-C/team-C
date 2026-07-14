import type { Layout, LayoutItem } from "react-grid-layout";
import type {
  DashboardLayoutDto,
  DashboardLayoutPutRequest as GeneratedDashboardLayoutPutRequest,
  DashboardWidgetLayoutDto,
} from "../contracts";

export const OVERVIEW_DASHBOARD_KEY = "overview";
export const OVERVIEW_LAYOUT_VERSION = 1;
export const DESKTOP_COLUMNS = 12;
export const TABLET_COLUMNS = 6;
export const MAX_LAYOUT_ROWS = 256;

export type WidgetDisplayMode = "compact" | "standard" | "expanded";
export type WidgetKind = "edr" | "kpi" | "donut" | "time-series" | "distribution" | "list" | "guidance";

export type DashboardWidgetLayout = DashboardWidgetLayoutDto;
export type DashboardLayoutResponse = DashboardLayoutDto;
export type DashboardLayoutPutRequest = GeneratedDashboardLayoutPutRequest;

export interface OverviewWidgetDefinition {
  id: string;
  title: string;
  kind: WidgetKind;
  defaultLayout: Omit<DashboardWidgetLayout, "id" | "hidden">;
  minW: number;
  minH: number;
  maxW: number;
  maxH: number;
  hideable: boolean;
}

export const OVERVIEW_WIDGET_DEFINITIONS: readonly OverviewWidgetDefinition[] = [
  widget("edr-state", "EDR state", "edr", 0, 0, 12, 2, 6, 2, 12, 4),
  widget("kpi-events", "Events", "kpi", 0, 2, 2, 2, 1, 2, 4, 3),
  widget("kpi-alerts", "Alerts", "kpi", 2, 2, 2, 2, 1, 2, 4, 3),
  widget("kpi-open-incidents", "Open incidents", "kpi", 4, 2, 2, 2, 1, 2, 4, 3),
  widget("kpi-online-endpoints", "Online endpoints", "kpi", 6, 2, 2, 2, 1, 2, 4, 3),
  widget("kpi-event-failures", "Event failures", "kpi", 8, 2, 2, 2, 1, 2, 4, 3),
  widget("kpi-storage-buckets", "Storage buckets", "kpi", 10, 2, 2, 2, 1, 2, 4, 3),
  widget("alert-severity", "Alert severity", "donut", 0, 4, 4, 5, 3, 4, 6, 7),
  widget("event-volume", "Event volume", "time-series", 4, 4, 8, 5, 6, 4, 12, 8),
  widget("alert-volume", "Alert volume", "time-series", 0, 9, 6, 5, 6, 4, 12, 8),
  widget("incident-activity", "Incident activity", "time-series", 6, 9, 6, 5, 6, 4, 12, 8),
  widget("endpoint-risk", "Endpoint risk", "distribution", 0, 14, 4, 5, 3, 4, 6, 8),
  widget("highest-risk-endpoints", "Highest-risk endpoints", "list", 4, 14, 4, 5, 4, 4, 8, 8),
  widget("incident-queue", "Incident queue", "list", 8, 14, 4, 5, 4, 4, 8, 8),
  widget("response-guidance", "Response guidance summary", "guidance", 0, 19, 12, 5, 6, 4, 12, 9),
  widget("endpoint-operating-systems", "Endpoint operating systems", "distribution", 0, 24, 4, 4, 3, 4, 6, 7),
  widget("sensor-health", "Sensor health", "distribution", 4, 24, 4, 4, 3, 4, 6, 7),
  widget("top-rules", "Top rules", "distribution", 8, 24, 4, 4, 3, 4, 6, 7),
  widget("mitre-distribution", "MITRE detection distribution", "distribution", 0, 28, 6, 5, 4, 4, 8, 8),
  widget("process-network-signals", "Process and network signals", "distribution", 6, 28, 6, 5, 4, 4, 8, 8),
  widget("file-dns-l7-signals", "File, DNS, and L7 signals", "distribution", 0, 33, 6, 5, 4, 4, 8, 8),
  widget("failure-distribution", "Failure distribution", "distribution", 6, 33, 6, 5, 4, 4, 8, 8),
  widget("storage-distribution", "Storage distribution", "distribution", 0, 38, 6, 5, 4, 4, 8, 8),
] as const;

const DEFINITION_BY_ID = new Map(OVERVIEW_WIDGET_DEFINITIONS.map((definition) => [definition.id, definition]));
const REGISTRY_ORDER = new Map(OVERVIEW_WIDGET_DEFINITIONS.map((definition, index) => [definition.id, index]));

export function createDefaultOverviewLayout(): DashboardWidgetLayout[] {
  return OVERVIEW_WIDGET_DEFINITIONS.map((definition) => ({
    id: definition.id,
    ...definition.defaultLayout,
    hidden: false,
  }));
}

export function normalizeOverviewLayout(value: unknown): DashboardWidgetLayout[] {
  if (!Array.isArray(value)) return createDefaultOverviewLayout();
  const seen = new Set<string>();
  const merged: DashboardWidgetLayout[] = [];
  for (const raw of value) {
    if (!isRecord(raw) || typeof raw.id !== "string" || seen.has(raw.id)) continue;
    const definition = DEFINITION_BY_ID.get(raw.id);
    if (!definition) continue;
    seen.add(raw.id);
    const w = clampInteger(raw.w, definition.defaultLayout.w, definition.minW, Math.min(definition.maxW, 12));
    const h = clampInteger(raw.h, definition.defaultLayout.h, definition.minH, definition.maxH);
    merged.push({
      id: definition.id,
      x: clampInteger(raw.x, definition.defaultLayout.x, 0, 12 - w),
      y: clampInteger(raw.y, definition.defaultLayout.y, 0, MAX_LAYOUT_ROWS - h),
      w,
      h,
      hidden: definition.hideable ? raw.hidden === true : false,
    });
  }
  for (const definition of OVERVIEW_WIDGET_DEFINITIONS) {
    if (!seen.has(definition.id)) {
      merged.push({ id: definition.id, ...definition.defaultLayout, hidden: false });
    }
  }
  return compactVisibleWidgets(merged);
}

export function desktopGridLayout(widgets: readonly DashboardWidgetLayout[], editable: boolean): Layout {
  return widgets.filter((widgetLayout) => !widgetLayout.hidden).map((widgetLayout) => {
    const definition = requireDefinition(widgetLayout.id);
    return {
      i: widgetLayout.id,
      x: widgetLayout.x,
      y: widgetLayout.y,
      w: widgetLayout.w,
      h: widgetLayout.h,
      minW: definition.minW,
      minH: definition.minH,
      maxW: definition.maxW,
      maxH: definition.maxH,
      isDraggable: editable,
      isResizable: editable,
      isBounded: true,
      resizeHandles: ["se"],
    } satisfies LayoutItem;
  });
}

export function tabletGridLayout(widgets: readonly DashboardWidgetLayout[]): Layout {
  const columns = TABLET_COLUMNS;
  const visible = orderedVisibleWidgets(widgets);
  const flowed = flowWidgets(
    visible.map((item) => ({
      ...item,
      w: Math.max(1, Math.min(columns, Math.round((item.w * columns) / DESKTOP_COLUMNS))),
    })),
    columns,
  );
  return flowed.map((item) => ({
    i: item.id,
    x: item.x,
    y: item.y,
    w: item.w,
    h: item.h,
    minW: 1,
    minH: 2,
    maxW: columns,
    maxH: requireDefinition(item.id).maxH,
    isDraggable: false,
    isResizable: false,
    isBounded: true,
  }));
}

export function applyDesktopGridLayout(
  current: readonly DashboardWidgetLayout[],
  gridLayout: Layout,
): DashboardWidgetLayout[] {
  const byId = new Map(gridLayout.map((item) => [item.i, item]));
  return normalizeOverviewLayout(current.map((widgetLayout) => {
    const item = byId.get(widgetLayout.id);
    return item ? { ...widgetLayout, x: item.x, y: item.y, w: item.w, h: item.h } : widgetLayout;
  }));
}

export function setWidgetHidden(
  current: readonly DashboardWidgetLayout[],
  widgetId: string,
  hidden: boolean,
): DashboardWidgetLayout[] {
  const definition = requireDefinition(widgetId);
  if (hidden && !definition.hideable) return [...current];
  return normalizeOverviewLayout(current.map((item) => item.id === widgetId ? { ...item, hidden } : item));
}

export function restoreWidgetAtGridPosition(
  current: readonly DashboardWidgetLayout[],
  widgetId: string,
  position: Pick<DashboardWidgetLayout, "x" | "y" | "w" | "h">,
): DashboardWidgetLayout[] {
  const definition = requireDefinition(widgetId);
  return normalizeOverviewLayout(current.map((item) => {
    if (item.id !== widgetId) return item;
    const w = clampInteger(position.w, item.w, definition.minW, Math.min(definition.maxW, DESKTOP_COLUMNS));
    const h = clampInteger(position.h, item.h, definition.minH, definition.maxH);
    return {
      ...item,
      x: clampInteger(position.x, item.x, 0, DESKTOP_COLUMNS - w),
      y: clampInteger(position.y, item.y, 0, MAX_LAYOUT_ROWS - h),
      w,
      h,
      hidden: false,
    };
  }));
}

export function moveWidgetInOrder(
  current: readonly DashboardWidgetLayout[],
  widgetId: string,
  delta: -1 | 1,
): DashboardWidgetLayout[] {
  const visible = orderedVisibleWidgets(current);
  const from = visible.findIndex((item) => item.id === widgetId);
  if (from < 0) return [...current];
  const to = Math.max(0, Math.min(visible.length - 1, from + delta));
  if (from === to) return [...current];
  const [moved] = visible.splice(from, 1);
  if (!moved) return [...current];
  visible.splice(to, 0, moved);
  const flowed = flowWidgets(visible, DESKTOP_COLUMNS);
  const byId = new Map(flowed.map((item) => [item.id, item]));
  return current.map((item) => byId.get(item.id) ?? item);
}

export function resizeWidgetByStep(
  current: readonly DashboardWidgetLayout[],
  widgetId: string,
  dimension: "width" | "height",
  delta: -1 | 1,
): DashboardWidgetLayout[] {
  const definition = requireDefinition(widgetId);
  const resized = current.map((item) => {
    if (item.id !== widgetId) return item;
    if (dimension === "width") {
      const w = Math.max(definition.minW, Math.min(definition.maxW, item.w + delta));
      return { ...item, w, x: Math.min(item.x, DESKTOP_COLUMNS - w) };
    }
    const h = Math.max(definition.minH, Math.min(definition.maxH, item.h + delta));
    return { ...item, h };
  });
  return normalizeOverviewLayout(resized);
}

export function widgetDisplayMode(widgetLayout: DashboardWidgetLayout): WidgetDisplayMode {
  const definition = requireDefinition(widgetLayout.id);
  switch (definition.kind) {
    case "kpi":
      if (widgetLayout.w <= 1) return "compact";
      if (widgetLayout.w >= 4 && widgetLayout.h >= 3) return "expanded";
      return "standard";
    case "edr":
      if (widgetLayout.w < 10) return "compact";
      if (widgetLayout.h >= 3) return "expanded";
      return "standard";
    case "time-series":
      if (widgetLayout.w <= 4 || widgetLayout.h <= 4) return "compact";
      if (widgetLayout.w >= 10 || widgetLayout.h >= 7) return "expanded";
      return "standard";
    case "donut":
    case "distribution":
      if (widgetLayout.w <= 3 || widgetLayout.h <= 4) return "compact";
      if (widgetLayout.w >= 6 && widgetLayout.h >= 6) return "expanded";
      return "standard";
    case "list":
      if (widgetLayout.w <= 4 || widgetLayout.h <= 4) return "compact";
      if (widgetLayout.w >= 7 && widgetLayout.h >= 7) return "expanded";
      return "standard";
    case "guidance":
      if (widgetLayout.w <= 6 || widgetLayout.h <= 4) return "compact";
      if (widgetLayout.w >= 10 && widgetLayout.h >= 7) return "expanded";
      return "standard";
  }
}

export function orderedVisibleWidgets(widgets: readonly DashboardWidgetLayout[]): DashboardWidgetLayout[] {
  return widgets.filter((item) => !item.hidden).sort((first, second) => (
    first.y - second.y || first.x - second.x || registryIndex(first.id) - registryIndex(second.id)
  ));
}

export function layoutsEqual(
  first: readonly DashboardWidgetLayout[],
  second: readonly DashboardWidgetLayout[],
): boolean {
  if (first.length !== second.length) return false;
  return first.every((item, index) => {
    const other = second[index];
    return other !== undefined && item.id === other.id && item.x === other.x && item.y === other.y
      && item.w === other.w && item.h === other.h && item.hidden === other.hidden;
  });
}

function compactVisibleWidgets(widgets: DashboardWidgetLayout[]): DashboardWidgetLayout[] {
  const visible = orderedVisibleWidgets(widgets);
  const placed: DashboardWidgetLayout[] = [];
  for (const item of visible) {
    let candidate = { ...item, y: 0 };
    while (placed.some((other) => collides(candidate, other))) candidate = { ...candidate, y: candidate.y + 1 };
    placed.push(candidate);
  }
  const byId = new Map(placed.map((item) => [item.id, item]));
  return widgets.map((item) => byId.get(item.id) ?? item);
}

function flowWidgets(widgets: readonly DashboardWidgetLayout[], columns: number): DashboardWidgetLayout[] {
  let x = 0;
  let y = 0;
  let rowHeight = 0;
  return widgets.map((item) => {
    const w = Math.max(1, Math.min(columns, item.w));
    if (x + w > columns) {
      x = 0;
      y += rowHeight;
      rowHeight = 0;
    }
    const next = { ...item, x, y, w };
    x += w;
    rowHeight = Math.max(rowHeight, item.h);
    if (x >= columns) {
      x = 0;
      y += rowHeight;
      rowHeight = 0;
    }
    return next;
  });
}

function collides(first: DashboardWidgetLayout, second: DashboardWidgetLayout): boolean {
  return !(first.x + first.w <= second.x || second.x + second.w <= first.x
    || first.y + first.h <= second.y || second.y + second.h <= first.y);
}

function widget(
  id: string,
  title: string,
  kind: WidgetKind,
  x: number,
  y: number,
  w: number,
  h: number,
  minW: number,
  minH: number,
  maxW: number,
  maxH: number,
): OverviewWidgetDefinition {
  return { id, title, kind, defaultLayout: { x, y, w, h }, minW, minH, maxW, maxH, hideable: true };
}

function requireDefinition(widgetId: string): OverviewWidgetDefinition {
  const definition = DEFINITION_BY_ID.get(widgetId);
  if (!definition) throw new Error(`Unknown overview widget: ${widgetId}`);
  return definition;
}

function registryIndex(widgetId: string): number {
  return REGISTRY_ORDER.get(widgetId) ?? Number.MAX_SAFE_INTEGER;
}

function clampInteger(value: unknown, fallback: number, minimum: number, maximum: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.max(minimum, Math.min(maximum, Math.trunc(value)));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
