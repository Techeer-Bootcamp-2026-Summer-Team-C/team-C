import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  Clock3,
  EyeOff,
  GripVertical,
  Monitor,
  RefreshCw,
  RotateCcw,
  Save,
  Settings2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ResponsiveGridLayout,
  useContainerWidth,
  verticalCompactor,
  type Layout,
  type LayoutItem,
  type ResponsiveLayouts,
} from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import { useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { Popover } from "../components/primitives";
import { ErrorState, PageHeader, Skeleton, StaleWarning } from "../components/ui";
import type { EndpointDto } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import {
  applyDesktopGridLayout,
  createDefaultOverviewLayout,
  desktopGridLayout,
  layoutsEqual,
  mobileGridLayout,
  moveWidgetInOrder,
  normalizeOverviewLayout,
  OVERVIEW_DASHBOARD_KEY,
  OVERVIEW_LAYOUT_VERSION,
  resolveOverviewLayout,
  resizeWidgetByStep,
  restoreWidgetAtGridPosition,
  setWidgetHidden,
  tabletGridLayout,
  widgetDisplayMode,
  type DashboardLayoutResponse,
  type DashboardWidgetLayout,
} from "../features/dashboardLayout";
import {
  OVERVIEW_WIDGET_BY_ID,
  OVERVIEW_WIDGET_REGISTRY,
  type OverviewWidgetData,
} from "../features/overviewWidgetRegistry";
import { translate } from "../i18n/translations";
import { formatDateTime } from "../lib/format";
import { updateParams } from "../lib/url";
import { pollingInterval } from "../query/policy";

type DashboardBreakpoint = "lg" | "md" | "sm";
type SaveStatus = "idle" | "unsaved" | "saving" | "saved" | "error" | "conflict";
type MigrationStatus = "idle" | "pending" | "saving" | "failed" | "complete";
const DASHBOARD_BREAKPOINTS = { lg: 1080, md: 768, sm: 0 } as const;
const DASHBOARD_COLUMNS = { lg: 12, md: 6, sm: 1 } as const;
const DASHBOARD_MARGINS = { lg: [12, 12], md: [8, 8], sm: [8, 8] } as const;
const DASHBOARD_CONTAINER_PADDING = { lg: [0, 0], md: [0, 0], sm: [0, 0] } as const;
const DASHBOARD_WIDGET_MIME = "application/x-edr-dashboard-widget";
let dashboardMigrationNoticeState: "pending" | "complete" | null = null;
const autoMigratedLayoutResponses = new WeakSet<object>();
type Translate = ReturnType<typeof useI18n>["t"];
const defaultTranslate: Translate = (key, params) => translate("EN", key, params);

export function readOverviewEndpointId(params: URLSearchParams): number | undefined {
  const endpointId = Number(params.get("endpointId"));
  return Number.isInteger(endpointId) && endpointId > 0 ? endpointId : undefined;
}

export function OverviewPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const selectedEndpointId = readOverviewEndpointId(params);
  const scopedTimeQuery = {
    ...time.query,
    ...(selectedEndpointId ? { endpointId: selectedEndpointId } : {}),
  };
  const summaryQuery = { ...scopedTimeQuery, interval: time.interval };
  const dashboard = useQuery({ queryKey: ["dashboard", summaryQuery], queryFn: ({ signal }) => api.dashboard(summaryQuery, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const endpoints = useQuery({ queryKey: ["endpoint-summary", scopedTimeQuery], queryFn: ({ signal }) => api.endpointSummary(scopedTimeQuery, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const ingest = useQuery({ queryKey: ["ingest-summary", scopedTimeQuery], queryFn: ({ signal }) => api.ingestSummary(scopedTimeQuery, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const endpointInventory = useQuery({ queryKey: ["overview-endpoint-inventory"], queryFn: ({ signal }) => api.endpoints({ page: 1, size: 500, sortBy: "riskScore", sortOrder: "desc" }, signal), staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const incidentQuery = { ...scopedTimeQuery, status: "OPEN" as const, page: 1, size: 5, sortOrder: "desc" as const };
  const incidentQueue = useQuery({ queryKey: ["overview-incidents", incidentQuery], queryFn: ({ signal }) => api.incidents(incidentQuery, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const savedLayout = useQuery({
    queryKey: ["dashboard-layout", OVERVIEW_DASHBOARD_KEY],
    queryFn: ({ signal }) => api.dashboardLayout(OVERVIEW_DASHBOARD_KEY, signal),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  const allQueries = [dashboard, endpoints, ingest, endpointInventory, incidentQueue];
  const initialError = allQueries.map((query) => query.error).find(Boolean) ?? null;
  const loading = allQueries.some((query) => query.isPending);
  const refreshing = allQueries.some((query) => query.isFetching);
  const lastRefreshedAt = Math.max(...allQueries.map((query) => query.dataUpdatedAt));
  const refreshData = () => Promise.all(allQueries.map((query) => query.refetch()));

  const endpointOptions = endpointInventory.data?.data.items ?? [];
  const topEndpoints = selectedEndpointId
    ? endpointOptions.filter((endpoint) => endpoint.endpointId === selectedEndpointId)
    : endpointOptions.slice(0, 5);
  const widgetData = dashboard.data && endpoints.data && ingest.data && endpointInventory.data && incidentQueue.data ? {
    dashboard: dashboard.data.data,
    endpoints: endpoints.data.data,
    ingest: ingest.data.data,
    topEndpoints,
    incidentQueue: incidentQueue.data.data.items,
    selectedEndpointId,
  } satisfies OverviewWidgetData : null;

  return (
    <div className="page-stack">
      <PageHeader eyebrow={t("overview.eyebrow")} title={t("overview.title")} description={t("overview.description")} />
      {!time.valid ? <ErrorState error={new Error(t("filter.invalidRange"))} /> : null}
      {loading && time.valid ? <OverviewSkeleton /> : null}
      {initialError && allQueries.every((query) => !query.data) ? <ErrorState error={initialError} onRetry={() => void Promise.all(allQueries.map((query) => query.refetch()))} /> : null}
      {allQueries.some((query) => query.isRefetchError) && allQueries.every((query) => query.data) ? <StaleWarning error={initialError} onRetry={() => void Promise.all(allQueries.map((query) => query.refetch()))} /> : null}
      {widgetData ? <OverviewContent
        data={widgetData}
        endpointOptions={endpointOptions}
        layoutLoadError={savedLayout.error}
        layoutLoadedAt={savedLayout.dataUpdatedAt}
        layoutLoading={savedLayout.isPending}
        layoutResponse={savedLayout.data?.data}
        lastRefreshedAt={lastRefreshedAt}
        onRefresh={refreshData}
        onReloadLayout={async () => { await savedLayout.refetch(); }}
        params={params}
        refreshing={refreshing}
        selectedEndpointId={selectedEndpointId}
        setParams={setParams}
        timePreset={time.preset}
      /> : null}
    </div>
  );
}

function OverviewContent({ data, endpointOptions, layoutResponse, layoutLoadError, layoutLoadedAt, layoutLoading, lastRefreshedAt, onRefresh, onReloadLayout, params, refreshing, selectedEndpointId, setParams, timePreset }: {
  data: OverviewWidgetData;
  endpointOptions: EndpointDto[];
  layoutResponse: DashboardLayoutResponse | undefined;
  layoutLoadError: unknown;
  layoutLoadedAt: number;
  layoutLoading: boolean;
  lastRefreshedAt: number;
  onRefresh: () => Promise<unknown>;
  onReloadLayout: () => Promise<void>;
  params: URLSearchParams;
  refreshing: boolean;
  selectedEndpointId: number | undefined;
  setParams: (next: URLSearchParams) => void;
  timePreset: string;
}) {
  const { t } = useI18n();
  const editor = useDashboardLayoutEditor(layoutResponse, layoutLoadedAt, t, { autoMigrate: true });
  const { width, containerRef, mounted } = useContainerWidth({ initialWidth: 1200 });
  const [draggingWidgetId, setDraggingWidgetId] = useState<string | null>(null);
  const [hideDropActive, setHideDropActive] = useState(false);
  const hideZoneRef = useRef<HTMLElement | null>(null);
  const externalWidgetRef = useRef<string | null>(null);
  const breakpoint: DashboardBreakpoint = width >= DASHBOARD_BREAKPOINTS.lg ? "lg" : width >= DASHBOARD_BREAKPOINTS.md ? "md" : "sm";
  const desktopEditing = editor.isEditing && breakpoint === "lg";
  const finishEditing = editor.finishEditing;
  useEffect(() => {
    if (breakpoint !== "lg" && editor.isEditing) void finishEditing();
  }, [breakpoint, editor.isEditing, finishEditing]);
  const layouts = useMemo<ResponsiveLayouts<DashboardBreakpoint>>(() => ({
    lg: desktopGridLayout(editor.draft, desktopEditing),
    md: tabletGridLayout(editor.draft),
    sm: mobileGridLayout(editor.draft),
  }), [desktopEditing, editor.draft]);
  const activeLayout = layouts[breakpoint] ?? layouts.lg ?? [];
  const hiddenWidgets = editor.draft.filter((item) => item.hidden);
  const hiddenTrayHint = breakpoint !== "lg"
    ? (hiddenWidgets.length ? t("dashboardLayout.hiddenTablet") : t("dashboardLayout.arrangementDesktop"))
    : (draggingWidgetId ? t("dashboardLayout.dropHide") : hiddenWidgets.length ? t("dashboardLayout.hiddenCount", { count: hiddenWidgets.length }) : t("dashboardLayout.dragHide"));
  const canStartEditing = breakpoint === "lg" && !layoutLoading && !layoutLoadError && !["pending", "saving", "failed"].includes(editor.migrationStatus);
  const visibleWidgetKey = editor.draft.filter((item) => !item.hidden).map((item) => item.id).join("|");
  const commitGrid = editor.commitGrid;
  const dragConfig = useMemo(() => ({
    enabled: desktopEditing,
    bounded: true,
    handle: ".dashboard-widget-drag-surface",
    threshold: 0,
  }), [desktopEditing]);
  const resizeConfig = useMemo(() => ({ enabled: desktopEditing, handles: ["se"] as const }), [desktopEditing]);
  const dropConfig = useMemo(() => ({ enabled: desktopEditing, defaultItem: { w: 2, h: 2 } }), [desktopEditing]);

  const handleResizeStop = useCallback((layout: Layout) => {
    if (!desktopEditing) return;
    commitGrid(layout);
  }, [commitGrid, desktopEditing]);

  const handleGridDragStart = useCallback((_: Layout, __: LayoutItem | null, item: LayoutItem | null) => {
    setDraggingWidgetId(item?.i ?? null);
  }, []);

  const handleGridDrag = useCallback((
    _: Layout,
    __: LayoutItem | null,
    ___: LayoutItem | null,
    ____: LayoutItem | null,
    event: Event,
  ) => {
    setHideDropActive(isEventInside(event, hideZoneRef.current));
  }, []);

  const handleGridDragStop = useCallback((
    layout: Layout,
    _: LayoutItem | null,
    item: LayoutItem | null,
    __: LayoutItem | null,
    event: Event,
  ) => {
    if (!desktopEditing) return;
    const widgetId = item?.i ?? draggingWidgetId;
    const shouldHide = Boolean(widgetId && isEventInside(event, hideZoneRef.current));
    setDraggingWidgetId(null);
    setHideDropActive(false);
    if (shouldHide && widgetId) {
      editor.setHidden(widgetId, true);
      return;
    }
    commitGrid(layout);
  }, [commitGrid, desktopEditing, draggingWidgetId, editor]);

  const handleHiddenDragStart = useCallback((event: React.DragEvent<HTMLButtonElement>, widgetId: string) => {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(DASHBOARD_WIDGET_MIME, widgetId);
    event.dataTransfer.setData("text/plain", widgetId);
    externalWidgetRef.current = widgetId;
  }, []);

  const clearExternalDrag = useCallback(() => {
    externalWidgetRef.current = null;
  }, []);

  const handleDropDragOver = useCallback((event: React.DragEvent<Element>) => {
    if (!desktopEditing) return false;
    const widgetId = readDraggedWidgetId(event.dataTransfer, externalWidgetRef.current);
    const widget = widgetId ? editor.draft.find((item) => item.id === widgetId && item.hidden) : undefined;
    return widget ? { w: widget.w, h: widget.h } : false;
  }, [desktopEditing, editor.draft]);

  const handleExternalDrop = useCallback((layout: Layout, item: LayoutItem | undefined, event: Event) => {
    const dragEvent = event as DragEvent;
    const widgetId = readDraggedWidgetId(dragEvent.dataTransfer, externalWidgetRef.current);
    const widget = widgetId ? editor.draft.find((candidate) => candidate.id === widgetId && candidate.hidden) : undefined;
    const dropPosition = item ?? (widget ? gridPositionFromDropEvent(event, widget) : null);
    clearExternalDrag();
    if (!desktopEditing || !widgetId || !dropPosition) return;
    editor.restoreAt(widgetId, layout, dropPosition);
  }, [clearExternalDrag, desktopEditing, editor]);

  return (
    <>
      <section className={`overview-toolbar ${editor.isEditing ? "editing" : ""}`} aria-label={t("overview.toolbarAria")}>
        <div className="overview-toolbar-controls">
          <OverviewEndpointSelect
            endpointOptions={endpointOptions}
            onChange={(endpointId) => setParams(updateParams(params, { endpointId }))}
            selectedEndpointId={selectedEndpointId}
          />
          <Popover className="overview-toolbar-popover time" label={t("filter.timeRange")} trigger={<><Clock3 aria-hidden="true" size={15} /><span>{timePresetLabel(timePreset, t)}</span><ChevronDown aria-hidden="true" size={14} /></>}>
            <div className="overview-time-fields"><TimeFilterFields params={params} setParams={setParams} /></div>
          </Popover>
          <button aria-busy={refreshing} className="button ghost overview-refresh" disabled={refreshing} onClick={() => void onRefresh()} type="button"><RefreshCw aria-hidden="true" className={refreshing ? "spin" : ""} size={15} />{refreshing ? t("overview.refreshing") : t("overview.refresh")}</button>
          <span className="overview-refresh-meta">{t("overview.lastRefreshed", { time: lastRefreshedAt ? formatDateTime(new Date(lastRefreshedAt).toISOString()) : t("overview.notYet") })}<small>{t("overview.autoRefresh")}</small></span>
        </div>
        <div className="dashboard-editor-actions">
          {editor.isEditing ? <>
            <button className="button ghost dashboard-editor-only" disabled={editor.saveStatus === "saving"} onClick={editor.cancelEditing} type="button"><X aria-hidden="true" size={15} />{t("dashboardLayout.cancel")}</button>
            <button className="button ghost dashboard-editor-only" disabled={editor.saveStatus === "saving"} onClick={() => void editor.resetLayout()} type="button"><RotateCcw aria-hidden="true" size={15} />{t("dashboardLayout.resetDefault")}</button>
            <button className="button dashboard-editor-only" disabled={editor.saveStatus === "saving"} onClick={() => void editor.saveNow()} type="button"><Save aria-hidden="true" size={15} />{t("dashboardLayout.save")}</button>
            <button className="button primary dashboard-editor-only" onClick={() => void editor.finishEditing()} type="button">{t("dashboardLayout.done")}</button>
          </> : <button className="button dashboard-edit-button" disabled={!canStartEditing} onClick={editor.startEditing} type="button"><Settings2 aria-hidden="true" size={15} />{t("dashboardLayout.edit")}</button>}
        </div>
      </section>
      {layoutLoadError ? <div className="dashboard-layout-message error" role="alert"><span>{t("dashboardLayout.loadError")}</span><button className="button ghost" onClick={() => void onReloadLayout()} type="button"><RefreshCw aria-hidden="true" size={15} />{t("dashboardLayout.reload")}</button></div> : null}
      {editor.conflict ? <div className="dashboard-layout-message conflict" role="alert"><span>{t("dashboardLayout.conflict")}</span><button className="button" onClick={() => void editor.reload(onReloadLayout)} type="button"><RefreshCw aria-hidden="true" size={15} />{t("dashboardLayout.reloadLatest")}</button></div> : null}
      {editor.migrationStatus === "saving" || editor.migrationStatus === "pending" ? <div className="dashboard-layout-message" role="status">{t("dashboardLayout.migrationSaving")}</div> : null}
      {editor.migrationStatus === "failed" && !editor.conflict ? <div className="dashboard-layout-message error" role="alert"><span>{t("dashboardLayout.saveError")}</span><button className="button" onClick={() => void editor.retryMigration()} type="button">{t("dashboardLayout.migrationRetry")}</button></div> : null}
      {editor.migrationNotice ? <div className="dashboard-layout-message migration-success" role="status"><span><strong>{t("dashboardLayout.migrationSuccess")}</strong>{t("dashboardLayout.migrationDescription")}</span><button className="button ghost" onClick={editor.dismissMigrationNotice} type="button">{t("dashboardLayout.migrationDismiss")}</button></div> : null}
      {editor.errorMessage ? <div className="dashboard-layout-message error" role="alert">{editor.errorMessage}</div> : null}
      <div className="dashboard-save-status" aria-live="polite" role="status">{saveStatusText(editor.saveStatus, t)}</div>
      {editor.isEditing ? <aside
        aria-label={t("dashboardLayout.hiddenDropAria")}
        className={`hidden-widget-tray dashboard-editor-only ${hideDropActive ? "drop-active" : ""}`}
        ref={hideZoneRef}
      >
        <div><strong><EyeOff aria-hidden="true" size={16} />{t("dashboardLayout.hiddenWidgets")}</strong><span>{hiddenTrayHint}</span></div>
        {hiddenWidgets.length ? <ul>{hiddenWidgets.map((item) => {
          const registration = OVERVIEW_WIDGET_BY_ID.get(item.id);
          const title = registration ? t(registration.titleKey) : item.id;
          return <li key={item.id}><button
            aria-label={desktopEditing ? t("dashboardLayout.restoreDragAria", { title }) : t("dashboardLayout.restoreAria", { title })}
            className="hidden-widget-drag-item"
            draggable={desktopEditing}
            onClick={() => editor.setHidden(item.id, false)}
            onDragEnd={clearExternalDrag}
            onDragStart={(event) => handleHiddenDragStart(event, item.id)}
            type="button"
          ><GripVertical aria-hidden="true" size={15} /><span>{title}</span><small>{desktopEditing ? t("dashboardLayout.dragRestore") : t("dashboardLayout.selectRestore")}</small></button></li>;
        })}</ul> : <span className="hidden-widget-empty">{t("dashboardLayout.noHidden")}</span>}
      </aside> : null}
      <div className="dashboard-grid-shell" ref={containerRef}>
        {mounted ? <ResponsiveGridLayout<DashboardBreakpoint>
          key={`${breakpoint}:${visibleWidgetKey}`}
          breakpoints={DASHBOARD_BREAKPOINTS}
          className={`dashboard-grid ${desktopEditing ? "is-editing" : ""}`}
          cols={DASHBOARD_COLUMNS}
          compactor={verticalCompactor}
          containerPadding={DASHBOARD_CONTAINER_PADDING}
          dragConfig={dragConfig}
          dropConfig={dropConfig}
          layouts={layouts}
          maxRows={256}
          margin={DASHBOARD_MARGINS}
          onDrag={handleGridDrag}
          onDragStart={handleGridDragStart}
          onDragStop={handleGridDragStop}
          onDrop={handleExternalDrop}
          onDropDragOver={handleDropDragOver}
          onResizeStop={handleResizeStop}
          resizeConfig={resizeConfig}
          rowHeight={54}
          width={width}
        >
          {OVERVIEW_WIDGET_REGISTRY.filter((registration) => !editor.draft.find((item) => item.id === registration.id)?.hidden).map((registration) => {
            const savedItem = editor.draft.find((item) => item.id === registration.id);
            if (!savedItem) return null;
            const responsiveItem = activeLayout.find((item) => item.i === registration.id);
            const displayLayout = responsiveItem ? { ...savedItem, w: responsiveItem.w, h: responsiveItem.h } : savedItem;
            const mode = widgetDisplayMode(displayLayout);
            return <div className={`dashboard-widget ${mode}`} data-widget-id={registration.id} key={registration.id}>
              {desktopEditing ? <WidgetDragSurface
                hideable={registration.hideable}
                title={t(registration.titleKey)}
                widgetId={registration.id}
                onHide={() => editor.setHidden(registration.id, true)}
                onMove={(delta) => editor.move(registration.id, delta)}
                onResize={(dimension, delta) => editor.resize(registration.id, dimension, delta)}
              /> : null}
              <div className="dashboard-widget-content">{registration.render(data, mode, t)}</div>
            </div>;
          })}
        </ResponsiveGridLayout> : null}
      </div>
    </>
  );
}

export function OverviewEndpointSelect({ endpointOptions, selectedEndpointId, onChange }: {
  endpointOptions: EndpointDto[];
  selectedEndpointId: number | undefined;
  onChange: (endpointId: number | undefined) => void;
}) {
  const { t } = useI18n();
  const selectedEndpointExists = selectedEndpointId === undefined
    || endpointOptions.some((endpoint) => endpoint.endpointId === selectedEndpointId);
  return <label className="overview-endpoint-select">
    <Monitor aria-hidden="true" size={15} />
    <span className="sr-only">{t("overview.endpointScope")}</span>
    <select
      aria-label={t("overview.endpointScope")}
      onChange={(event) => onChange(event.target.value ? Number(event.target.value) : undefined)}
      value={selectedEndpointId ?? ""}
    >
      <option value="">{t("overview.allEndpoints")}</option>
      {!selectedEndpointExists && selectedEndpointId !== undefined
        ? <option value={selectedEndpointId}>{`Endpoint ${selectedEndpointId}`}</option>
        : null}
      {endpointOptions.map((endpoint) => (
        <option key={endpoint.endpointId} value={endpoint.endpointId}>
          {`${endpoint.hostname} · ID ${endpoint.endpointId}`}
        </option>
      ))}
    </select>
  </label>;
}

function WidgetDragSurface({ widgetId, title, hideable, onHide, onMove, onResize }: {
  widgetId: string;
  title: string;
  hideable: boolean;
  onHide: () => void;
  onMove: (delta: -1 | 1) => void;
  onResize: (dimension: "width" | "height", delta: -1 | 1) => void;
}) {
  const { t } = useI18n();
  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (hideable && (event.key === "Delete" || event.key === "Backspace")) {
      event.preventDefault();
      onHide();
      return;
    }
    if (!event.altKey || !event.key.startsWith("Arrow")) return;
    event.preventDefault();
    if (event.shiftKey) {
      if (event.key === "ArrowLeft") onResize("width", -1);
      if (event.key === "ArrowRight") onResize("width", 1);
      if (event.key === "ArrowUp") onResize("height", -1);
      if (event.key === "ArrowDown") onResize("height", 1);
    } else {
      onMove(event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1);
    }
  };
  return <>
    <button
      aria-describedby={`${widgetId}-keyboard-help`}
      aria-label={t("dashboardLayout.moveAria", { title })}
      className="dashboard-widget-drag-surface dashboard-editor-only"
      onKeyDown={handleKeyDown}
      title={t("dashboardLayout.dragTitle", { title })}
      type="button"
    ><span aria-hidden="true"><GripVertical size={16} /></span></button>
    <span className="sr-only" id={`${widgetId}-keyboard-help`}>{t("dashboardLayout.keyboardHelp")}</span>
  </>;
}

function isEventInside(event: Event, element: HTMLElement | null): boolean {
  if (!element || !("clientX" in event) || !("clientY" in event)) return false;
  const clientX = Number(event.clientX);
  const clientY = Number(event.clientY);
  if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) return false;
  const bounds = element.getBoundingClientRect();
  return clientX >= bounds.left && clientX <= bounds.right && clientY >= bounds.top && clientY <= bounds.bottom;
}

function readDraggedWidgetId(dataTransfer: DataTransfer | null, fallback: string | null): string | null {
  return dataTransfer?.getData(DASHBOARD_WIDGET_MIME) || dataTransfer?.getData("text/plain") || fallback;
}

function gridPositionFromDropEvent(
  event: Event,
  widget: DashboardWidgetLayout,
): Pick<DashboardWidgetLayout, "x" | "y" | "w" | "h"> | null {
  if (!(event.target instanceof Element) || !("clientX" in event) || !("clientY" in event)) return null;
  const grid = event.target.closest<HTMLElement>(".react-grid-layout");
  if (!grid) return null;
  const bounds = grid.getBoundingClientRect();
  const margin = 12;
  const padding = 12;
  const rowHeight = 54;
  const columnWidth = (bounds.width - (margin * 11) - (padding * 2)) / 12;
  const x = Math.floor((Number(event.clientX) - bounds.left - padding + margin) / (columnWidth + margin));
  const y = Math.floor((Number(event.clientY) - bounds.top - padding + margin) / (rowHeight + margin));
  return {
    x: Math.max(0, Math.min(12 - widget.w, x)),
    y: Math.max(0, y),
    w: widget.w,
    h: widget.h,
  };
}

export function useDashboardLayoutEditor(
  layoutResponse: DashboardLayoutResponse | undefined,
  layoutLoadedAt = layoutResponse ? 1 : 0,
  t: Translate = defaultTranslate,
  options: { autoMigrate?: boolean } = {},
) {
  const [draft, setDraftState] = useState<DashboardWidgetLayout[]>(createDefaultOverviewLayout);
  const [isEditing, setIsEditing] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [conflict, setConflict] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [migrationStatus, setMigrationStatus] = useState<MigrationStatus>("idle");
  const [migrationNotice, setMigrationNotice] = useState(false);
  const [migrationRequest, setMigrationRequest] = useState<number | null>(null);
  const draftRef = useRef(draft);
  const committedRef = useRef(draft);
  const revisionRef = useRef(0);
  const editBaselineRef = useRef(draft);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightRef = useRef<DashboardWidgetLayout[] | null>(null);
  const queuedRef = useRef<DashboardWidgetLayout[] | null>(null);
  const drainPromiseRef = useRef<Promise<boolean> | null>(null);
  const persistRef = useRef<(candidate: DashboardWidgetLayout[]) => Promise<boolean>>(async () => true);
  const layoutResponseRef = useRef(layoutResponse);
  const migrationAttemptedAtRef = useRef<number | null>(null);
  const migrationPromiseRef = useRef<Promise<boolean> | null>(null);
  layoutResponseRef.current = layoutResponse;

  const setDraft = useCallback((next: DashboardWidgetLayout[]) => {
    draftRef.current = next;
    setDraftState(next);
  }, []);

  useEffect(() => {
    const response = layoutResponseRef.current;
    if (!response || layoutLoadedAt === 0) return;
    const resolved = resolveOverviewLayout(response.layoutVersion, response.widgets);
    const merged = resolved.widgets;
    revisionRef.current = response.revision;
    committedRef.current = merged;
    editBaselineRef.current = merged;
    setDraft(merged);
    setConflict(false);
    setErrorMessage(null);
    setSaveStatus("idle");
    if (resolved.migrationRequired && options.autoMigrate
      && migrationAttemptedAtRef.current !== layoutLoadedAt && !autoMigratedLayoutResponses.has(response)) {
      migrationAttemptedAtRef.current = layoutLoadedAt;
      autoMigratedLayoutResponses.add(response);
      setMigrationStatus("pending");
      setMigrationRequest(layoutLoadedAt);
    } else if (!resolved.migrationRequired) {
      setMigrationStatus("idle");
      if (readMigrationNotice() === "pending") setMigrationNotice(true);
    }
  }, [layoutLoadedAt, options.autoMigrate, setDraft]);

  const persistNow = useCallback((candidate: DashboardWidgetLayout[]): Promise<boolean> => {
    const normalized = normalizeOverviewLayout(candidate);
    const activeDrain = drainPromiseRef.current;
    if (activeDrain) {
      if (!inFlightRef.current || !layoutsEqual(normalized, inFlightRef.current)) {
        queuedRef.current = normalized;
      }
      return activeDrain;
    }
    queuedRef.current = normalized;
    const drain = (async () => {
      let succeeded = true;
      while (queuedRef.current) {
        const next = queuedRef.current;
        queuedRef.current = null;
        inFlightRef.current = next;
        setSaveStatus("saving");
        setErrorMessage(null);
        try {
          const response = await api.saveDashboardLayout(OVERVIEW_DASHBOARD_KEY, {
            layoutVersion: OVERVIEW_LAYOUT_VERSION,
            revision: revisionRef.current,
            widgets: next,
          });
          const saved = normalizeOverviewLayout(response.data.widgets);
          revisionRef.current = response.data.revision;
          committedRef.current = saved;
          if (!queuedRef.current) {
            setDraft(saved);
            setSaveStatus("saved");
          }
        } catch (error) {
          queuedRef.current = null;
          setDraft(committedRef.current);
          if (error instanceof ApiError && error.status === 409) {
            setConflict(true);
            setSaveStatus("conflict");
          } else {
            setErrorMessage(error instanceof Error ? error.message : t("dashboardLayout.saveError"));
            setSaveStatus("error");
          }
          succeeded = false;
          break;
        } finally {
          inFlightRef.current = null;
        }
      }
      drainPromiseRef.current = null;
      return succeeded;
    })();
    drainPromiseRef.current = drain;
    return drain;
  }, [setDraft, t]);

  useEffect(() => { persistRef.current = persistNow; }, [persistNow]);
  const runMigration = useCallback((): Promise<boolean> => {
    if (migrationPromiseRef.current) return migrationPromiseRef.current;
    const migration = (async () => {
      setMigrationStatus("saving");
      const succeeded = await persistRef.current(draftRef.current);
      if (succeeded) {
        writeMigrationNotice("pending");
        setMigrationNotice(true);
        setMigrationStatus("complete");
      } else {
        setMigrationStatus("failed");
      }
      return succeeded;
    })();
    const trackedMigration = migration.finally(() => {
      if (migrationPromiseRef.current === trackedMigration) migrationPromiseRef.current = null;
    });
    migrationPromiseRef.current = trackedMigration;
    return trackedMigration;
  }, []);
  useEffect(() => {
    if (migrationRequest === null) return;
    setMigrationRequest(null);
    void runMigration();
  }, [migrationRequest, runMigration]);
  useEffect(() => () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current); }, []);
  useEffect(() => {
    if (saveStatus !== "unsaved" && saveStatus !== "saving") return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [saveStatus]);

  const queueSave = useCallback((next: DashboardWidgetLayout[]) => {
    setDraft(next);
    setSaveStatus("unsaved");
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => { void persistRef.current(next); }, 650);
  }, [setDraft]);

  const saveNow = useCallback(async () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = null;
    return persistRef.current(draftRef.current);
  }, []);

  const finishEditing = useCallback(async () => {
    const saved = await saveNow();
    if (saved) setIsEditing(false);
  }, [saveNow]);

  return {
    draft,
    isEditing,
    saveStatus,
    conflict,
    errorMessage,
    migrationStatus,
    migrationNotice,
    retryMigration: runMigration,
    dismissMigrationNotice() {
      writeMigrationNotice("complete");
      setMigrationNotice(false);
    },
    startEditing() {
      editBaselineRef.current = committedRef.current;
      setIsEditing(true);
      setErrorMessage(null);
    },
    finishEditing,
    cancelEditing() {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
      queuedRef.current = null;
      const baseline = editBaselineRef.current;
      setDraft(baseline);
      setIsEditing(false);
      if (drainPromiseRef.current || !layoutsEqual(baseline, committedRef.current)) void persistRef.current(baseline);
      else setSaveStatus("idle");
    },
    commitGrid: useCallback((layout: Layout) => {
      queueSave(applyDesktopGridLayout(draftRef.current, layout));
    }, [queueSave]),
    restoreAt: useCallback((
      widgetId: string,
      layout: Layout,
      droppedItem: Pick<DashboardWidgetLayout, "x" | "y" | "w" | "h"> & { i?: string },
    ) => {
      const withoutPlaceholder = layout.filter((item) => item.i !== (droppedItem.i ?? "__dropping-elem__"));
      const movedGrid = applyDesktopGridLayout(draftRef.current, withoutPlaceholder);
      queueSave(restoreWidgetAtGridPosition(movedGrid, widgetId, droppedItem));
    }, [queueSave]),
    setHidden(widgetId: string, hidden: boolean) {
      queueSave(setWidgetHidden(draftRef.current, widgetId, hidden));
    },
    move(widgetId: string, delta: -1 | 1) {
      queueSave(moveWidgetInOrder(draftRef.current, widgetId, delta));
    },
    resize(widgetId: string, dimension: "width" | "height", delta: -1 | 1) {
      queueSave(resizeWidgetByStep(draftRef.current, widgetId, dimension, delta));
    },
    saveNow,
    async resetLayout() {
      if (!window.confirm(t("dashboardLayout.resetConfirm"))) return;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
      queuedRef.current = null;
      setSaveStatus("saving");
      try {
        const response = await api.resetDashboardLayout(OVERVIEW_DASHBOARD_KEY);
        const defaults = normalizeOverviewLayout(response.data.widgets);
        revisionRef.current = response.data.revision;
        committedRef.current = defaults;
        editBaselineRef.current = defaults;
        setDraft(defaults);
        setSaveStatus("saved");
        setConflict(false);
        setErrorMessage(null);
      } catch (error) {
        setDraft(committedRef.current);
        setSaveStatus("error");
        setErrorMessage(error instanceof Error ? error.message : t("dashboardLayout.resetError"));
      }
    },
    async reload(reloadLayout: () => Promise<void>) {
      await reloadLayout();
      setConflict(false);
      setErrorMessage(null);
    },
  };
}

function timePresetLabel(preset: string, t: Translate): string {
  if (preset === "LATEST_15M") return t("filter.latest15Minutes");
  if (preset === "LATEST_1H") return t("filter.latestHour");
  if (preset === "LATEST_7D") return t("filter.latest7Days");
  if (preset === "CUSTOM") return t("filter.customUtcRange");
  return t("filter.latest24Hours");
}

function readMigrationNotice(): string | null {
  return dashboardMigrationNoticeState;
}

function writeMigrationNotice(value: "pending" | "complete") {
  dashboardMigrationNoticeState = value;
}

function saveStatusText(status: SaveStatus, t: Translate): string {
  if (status === "unsaved") return t("dashboardLayout.statusUnsaved");
  if (status === "saving") return t("dashboardLayout.statusSaving");
  if (status === "saved") return t("dashboardLayout.statusSaved");
  if (status === "error") return t("dashboardLayout.statusError");
  if (status === "conflict") return t("dashboardLayout.statusConflict");
  return "";
}

function OverviewSkeleton() {
  return <><Skeleton rows={2} /><section className="kpi-grid">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} rows={2} />)}</section><section className="overview-grid"><Skeleton rows={5} /><Skeleton rows={5} /><Skeleton rows={5} /></section></>;
}
