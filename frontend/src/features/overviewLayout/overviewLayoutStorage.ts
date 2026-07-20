import {
  DEFAULT_DASHBOARD_ID,
  OVERVIEW_GRID_COLUMNS,
  OVERVIEW_GRID_MAX_ROWS,
  createOverviewGridOccupancy,
  findAvailableOverviewWidgetPosition,
  isOverviewWidgetType,
  occupyOverviewGridRegion,
  widgetDefinition,
  type CustomDashboardWidget,
  type CustomOverviewDashboard,
  type OverviewDashboardStoreV1,
  type OverviewWidgetType,
} from "./overviewLayoutModel";

const DASHBOARDS_STORAGE_PREFIX = "edr.overviewDashboards.v1.user.";
const ACTIVE_DASHBOARD_STORAGE_PREFIX = "edr.overviewActiveDashboard.v1.user.";

interface StorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

export interface StoredOverviewLayoutState {
  dashboards: CustomOverviewDashboard[];
  activeDashboardId: string;
}

export function dashboardsStorageKey(userId: number): string {
  return `${DASHBOARDS_STORAGE_PREFIX}${userId}`;
}

export function activeDashboardStorageKey(userId: number): string {
  return `${ACTIVE_DASHBOARD_STORAGE_PREFIX}${userId}`;
}

export function readOverviewLayoutState(userId: number, storage?: StorageLike): StoredOverviewLayoutState {
  try {
    const targetStorage = storage ?? window.localStorage;
    const dashboards = parseOverviewDashboardStore(targetStorage.getItem(dashboardsStorageKey(userId))).dashboards;
    const storedActive = targetStorage.getItem(activeDashboardStorageKey(userId));
    return {
      dashboards,
      activeDashboardId: storedActive && dashboards.some((dashboard) => dashboard.id === storedActive)
        ? storedActive
        : DEFAULT_DASHBOARD_ID,
    };
  } catch {
    return { dashboards: [], activeDashboardId: DEFAULT_DASHBOARD_ID };
  }
}

export function writeOverviewLayoutState(userId: number, state: StoredOverviewLayoutState, storage?: StorageLike): void {
  try {
    const targetStorage = storage ?? window.localStorage;
    const store: OverviewDashboardStoreV1 = { version: 1, dashboards: state.dashboards };
    targetStorage.setItem(dashboardsStorageKey(userId), JSON.stringify(store));
    targetStorage.setItem(activeDashboardStorageKey(userId), state.activeDashboardId);
  } catch {
    // In-memory dashboards remain available when browser storage is unavailable.
  }
}

export function parseOverviewDashboardStore(raw: string | null): OverviewDashboardStoreV1 {
  if (!raw) return { version: 1, dashboards: [] };
  try {
    return normalizeOverviewDashboardStore(JSON.parse(raw));
  } catch {
    return { version: 1, dashboards: [] };
  }
}

export function normalizeOverviewDashboardStore(value: unknown): OverviewDashboardStoreV1 {
  if (!isRecord(value) || value.version !== 1 || !Array.isArray(value.dashboards)) {
    return { version: 1, dashboards: [] };
  }

  const dashboardIds = new Set<string>();
  const dashboards: CustomOverviewDashboard[] = [];
  for (const candidate of value.dashboards) {
    const dashboard = normalizeDashboard(candidate, dashboardIds);
    if (dashboard) dashboards.push(dashboard);
  }
  return { version: 1, dashboards };
}

function normalizeDashboard(value: unknown, dashboardIds: Set<string>): CustomOverviewDashboard | null {
  if (!isRecord(value)) return null;
  const id = normalizeText(value.id, 120);
  const name = normalizeText(value.name, 80);
  if (!id || !name || dashboardIds.has(id) || !Array.isArray(value.widgets)) return null;

  const widgetIds = new Set<string>();
  const widgetTypes = new Set<OverviewWidgetType>();
  const widgets: CustomDashboardWidget[] = [];
  const occupancy = createOverviewGridOccupancy();
  const unplaceableSizes = new Set<string>();
  for (const candidate of value.widgets) {
    if (isRecord(candidate) && isOverviewWidgetType(candidate.type) && widgetTypes.has(candidate.type)) continue;
    const widget = normalizeWidget(candidate, widgetIds);
    if (!widget) continue;
    const sizeKey = `${widget.w}x${widget.h}`;
    if (unplaceableSizes.has(sizeKey)) continue;
    const position = findAvailableOverviewWidgetPosition(widget, widgets, occupancy);
    if (!position) {
      unplaceableSizes.add(sizeKey);
      continue;
    }
    const placedWidget = { ...widget, ...position };
    widgets.push(placedWidget);
    widgetTypes.add(placedWidget.type);
    occupyOverviewGridRegion(occupancy, placedWidget);
  }
  if (!widgets.length) return null;

  dashboardIds.add(id);
  const fallbackDate = new Date(0).toISOString();
  return {
    id,
    name,
    widgets,
    createdAt: normalizeDate(value.createdAt) ?? fallbackDate,
    updatedAt: normalizeDate(value.updatedAt) ?? fallbackDate,
  };
}

function normalizeWidget(value: unknown, widgetIds: Set<string>): CustomDashboardWidget | null {
  if (!isRecord(value) || !isOverviewWidgetType(value.type)) return null;
  const uid = normalizeText(value.uid, 160);
  if (!uid || widgetIds.has(uid)) return null;
  const definition = widgetDefinition(value.type);
  const w = clampInteger(value.w, definition.minW, Math.min(definition.maxW, OVERVIEW_GRID_COLUMNS), definition.defaultW);
  const h = clampInteger(value.h, definition.minH, definition.maxH, definition.defaultH);
  const x = clampInteger(value.x, 0, OVERVIEW_GRID_COLUMNS - w, 0);
  const y = clampInteger(value.y, 0, OVERVIEW_GRID_MAX_ROWS - h, 0);
  widgetIds.add(uid);
  return { uid, type: value.type, x, y, w, h };
}

function clampInteger(value: unknown, min: number, max: number, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.min(Math.max(Math.round(value), min), max);
}

function normalizeText(value: unknown, maxLength: number): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().slice(0, maxLength);
  return normalized || null;
}

function normalizeDate(value: unknown): string | null {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) return null;
  return new Date(value).toISOString();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
