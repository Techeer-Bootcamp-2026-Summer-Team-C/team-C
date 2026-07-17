import type { TranslationKey } from "../../i18n/translations";

export const OVERVIEW_WIDGET_TYPES = [
  "edr-state",
  "kpi-alerts",
  "kpi-critical-alerts",
  "kpi-high-risk-endpoints",
  "kpi-open-incidents",
  "detection-activity",
  "alert-severity",
  "highest-risk-endpoints",
  "incident-queue",
] as const;

export type OverviewWidgetType = typeof OVERVIEW_WIDGET_TYPES[number];

export interface OverviewWidgetDefinition {
  type: OverviewWidgetType;
  titleKey: TranslationKey;
  defaultW: number;
  defaultH: number;
  minW: number;
  minH: number;
  maxW: number;
  maxH: number;
}

export interface CustomDashboardWidget {
  uid: string;
  type: OverviewWidgetType;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface CustomOverviewDashboard {
  id: string;
  name: string;
  widgets: CustomDashboardWidget[];
  createdAt: string;
  updatedAt: string;
}

export interface OverviewDashboardStoreV1 {
  version: 1;
  dashboards: CustomOverviewDashboard[];
}

export const OVERVIEW_GRID_COLUMNS = 12;
export const OVERVIEW_GRID_MAX_ROWS = 256;
export const DEFAULT_DASHBOARD_ID = "default";
const OVERVIEW_GRID_CELL_COUNT = OVERVIEW_GRID_COLUMNS * OVERVIEW_GRID_MAX_ROWS;

export const OVERVIEW_WIDGET_DEFINITIONS: readonly OverviewWidgetDefinition[] = [
  { type: "edr-state", titleKey: "edrState.current", defaultW: 12, defaultH: 4, minW: 12, minH: 4, maxW: 12, maxH: 8 },
  { type: "kpi-alerts", titleKey: "overview.totalAlerts", defaultW: 3, defaultH: 2, minW: 3, minH: 2, maxW: 6, maxH: 5 },
  { type: "kpi-critical-alerts", titleKey: "overview.criticalAlerts", defaultW: 3, defaultH: 2, minW: 3, minH: 2, maxW: 6, maxH: 5 },
  { type: "kpi-high-risk-endpoints", titleKey: "overview.highRiskEndpoints", defaultW: 3, defaultH: 2, minW: 3, minH: 2, maxW: 6, maxH: 5 },
  { type: "kpi-open-incidents", titleKey: "overview.openIncidents", defaultW: 3, defaultH: 2, minW: 3, minH: 2, maxW: 6, maxH: 5 },
  { type: "detection-activity", titleKey: "overview.detectionActivity", defaultW: 8, defaultH: 10, minW: 6, minH: 10, maxW: 12, maxH: 12 },
  { type: "alert-severity", titleKey: "overview.alertSeverity", defaultW: 4, defaultH: 7, minW: 4, minH: 7, maxW: 8, maxH: 12 },
  { type: "highest-risk-endpoints", titleKey: "overview.highestRiskEndpoints", defaultW: 6, defaultH: 7, minW: 6, minH: 7, maxW: 12, maxH: 12 },
  { type: "incident-queue", titleKey: "overview.incidentQueueWidget", defaultW: 6, defaultH: 7, minW: 6, minH: 7, maxW: 12, maxH: 12 },
] as const;

export function isOverviewWidgetType(value: unknown): value is OverviewWidgetType {
  return typeof value === "string" && (OVERVIEW_WIDGET_TYPES as readonly string[]).includes(value);
}

export function widgetDefinition(type: OverviewWidgetType): OverviewWidgetDefinition {
  const definition = OVERVIEW_WIDGET_DEFINITIONS.find((candidate) => candidate.type === type);
  if (!definition) throw new Error(`Unknown Overview widget type: ${type}`);
  return definition;
}

export function createOverviewWidget(type: OverviewWidgetType): CustomDashboardWidget {
  const definition = widgetDefinition(type);
  return {
    uid: createOverviewId("widget"),
    type,
    x: 0,
    y: 0,
    w: definition.defaultW,
    h: definition.defaultH,
  };
}

export function findAvailableOverviewWidgetPosition(
  widget: Pick<CustomDashboardWidget, "x" | "y" | "w" | "h">,
  widgets: readonly CustomDashboardWidget[],
  occupancy = createOverviewGridOccupancy(widgets),
): Pick<CustomDashboardWidget, "x" | "y"> | null {
  if (!Number.isInteger(widget.w) || !Number.isInteger(widget.h) || widget.w < 1 || widget.h < 1 || widget.w > OVERVIEW_GRID_COLUMNS || widget.h > OVERVIEW_GRID_MAX_ROWS) return null;
  const requestedX = Math.min(Math.max(widget.x, 0), OVERVIEW_GRID_COLUMNS - widget.w);
  const requestedY = Math.min(Math.max(widget.y, 0), OVERVIEW_GRID_MAX_ROWS - widget.h);
  const xCandidates = Array.from({ length: OVERVIEW_GRID_COLUMNS - widget.w + 1 }, (_, x) => x)
    .sort((a, b) => Math.abs(a - requestedX) - Math.abs(b - requestedX));
  const yCandidates = Array.from({ length: OVERVIEW_GRID_MAX_ROWS - widget.h + 1 }, (_, y) => y)
    .sort((a, b) => Math.abs(a - requestedY) - Math.abs(b - requestedY));

  for (const y of yCandidates) {
    for (const x of xCandidates) {
      if (overviewGridRegionAvailable(occupancy, x, y, widget.w, widget.h)) return { x, y };
    }
  }
  return null;
}

export function createOverviewGridOccupancy(widgets: readonly Pick<CustomDashboardWidget, "x" | "y" | "w" | "h">[] = []): Uint8Array {
  const occupancy = new Uint8Array(OVERVIEW_GRID_CELL_COUNT);
  widgets.forEach((widget) => occupyOverviewGridRegion(occupancy, widget));
  return occupancy;
}

export function occupyOverviewGridRegion(
  occupancy: Uint8Array,
  widget: Pick<CustomDashboardWidget, "x" | "y" | "w" | "h">,
): void {
  const left = Math.max(0, Math.floor(widget.x));
  const top = Math.max(0, Math.floor(widget.y));
  const right = Math.min(OVERVIEW_GRID_COLUMNS, Math.ceil(widget.x + widget.w));
  const bottom = Math.min(OVERVIEW_GRID_MAX_ROWS, Math.ceil(widget.y + widget.h));
  for (let y = top; y < bottom; y += 1) {
    for (let x = left; x < right; x += 1) occupancy[(y * OVERVIEW_GRID_COLUMNS) + x] = 1;
  }
}

function overviewGridRegionAvailable(occupancy: Uint8Array, x: number, y: number, w: number, h: number): boolean {
  for (let row = y; row < y + h; row += 1) {
    for (let column = x; column < x + w; column += 1) {
      if (occupancy[(row * OVERVIEW_GRID_COLUMNS) + column]) return false;
    }
  }
  return true;
}

export function overviewWidgetsOverlap(
  left: Pick<CustomDashboardWidget, "x" | "y" | "w" | "h">,
  right: Pick<CustomDashboardWidget, "x" | "y" | "w" | "h">,
): boolean {
  return left.x < right.x + right.w
    && left.x + left.w > right.x
    && left.y < right.y + right.h
    && left.y + left.h > right.y;
}

export function createOverviewId(prefix: "dashboard" | "widget"): string {
  const value = globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `${prefix}-${value}`;
}
