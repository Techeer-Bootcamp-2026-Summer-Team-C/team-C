import { useQuery } from "@tanstack/react-query";
import {
  EyeOff,
  GripVertical,
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
import { ErrorState, GlobalFilterBar, PageHeader, Skeleton, StaleWarning } from "../components/ui";
import { useI18n } from "../i18n/LocaleContext";
import {
  applyDesktopGridLayout,
  createDefaultOverviewLayout,
  desktopGridLayout,
  layoutsEqual,
  moveWidgetInOrder,
  normalizeOverviewLayout,
  OVERVIEW_DASHBOARD_KEY,
  OVERVIEW_LAYOUT_VERSION,
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
import { pollingInterval } from "../query/policy";

type DashboardBreakpoint = "lg" | "md";
type SaveStatus = "idle" | "unsaved" | "saving" | "saved" | "error" | "conflict";
const DASHBOARD_BREAKPOINTS = { lg: 1200, md: 0 } as const;
const DASHBOARD_COLUMNS = { lg: 12, md: 6 } as const;
const DASHBOARD_MARGINS = { lg: [12, 12], md: [10, 10] } as const;
const DASHBOARD_WIDGET_MIME = "application/x-edr-dashboard-widget";
type Translate = ReturnType<typeof useI18n>["t"];
const defaultTranslate: Translate = (key, params) => translate("EN", key, params);

export function OverviewPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const summaryQuery = { ...time.query, interval: time.interval };
  const dashboard = useQuery({ queryKey: ["dashboard", summaryQuery], queryFn: ({ signal }) => api.dashboard(summaryQuery, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const endpoints = useQuery({ queryKey: ["endpoint-summary", time.query], queryFn: ({ signal }) => api.endpointSummary(time.query, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const ingest = useQuery({ queryKey: ["ingest-summary", time.query], queryFn: ({ signal }) => api.ingestSummary(time.query, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const topEndpoints = useQuery({ queryKey: ["overview-endpoint-risk"], queryFn: ({ signal }) => api.endpoints({ page: 1, size: 5, sortBy: "riskScore", sortOrder: "desc" }, signal), staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const incidentQueue = useQuery({ queryKey: ["overview-incidents", time.query], queryFn: ({ signal }) => api.incidents({ ...time.query, status: "OPEN", page: 1, size: 5, sortOrder: "desc" }, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const savedLayout = useQuery({
    queryKey: ["dashboard-layout", OVERVIEW_DASHBOARD_KEY],
    queryFn: ({ signal }) => api.dashboardLayout(OVERVIEW_DASHBOARD_KEY, signal),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  const allQueries = [dashboard, endpoints, ingest, topEndpoints, incidentQueue];
  const initialError = allQueries.map((query) => query.error).find(Boolean) ?? null;
  const loading = allQueries.some((query) => query.isPending);
  const lastRefreshedAt = Math.max(...allQueries.map((query) => query.dataUpdatedAt));

  const widgetData = dashboard.data && endpoints.data && ingest.data && topEndpoints.data && incidentQueue.data ? {
    dashboard: dashboard.data.data,
    endpoints: endpoints.data.data,
    ingest: ingest.data.data,
    topEndpoints: topEndpoints.data.data.items,
    incidentQueue: incidentQueue.data.data.items,
  } satisfies OverviewWidgetData : null;

  return (
    <div className="page-stack">
      <PageHeader eyebrow={t("overview.eyebrow")} title={t("overview.title")} description={t("overview.description")} actions={<span className="last-refreshed">{t("overview.lastRefreshed", { time: lastRefreshedAt ? formatDateTime(new Date(lastRefreshedAt).toISOString()) : t("overview.notYet") })}</span>} />
      <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}><TimeFilterFields params={params} setParams={setParams} /></GlobalFilterBar>
      {!time.valid ? <ErrorState error={new Error(t("filter.invalidRange"))} /> : null}
      {loading && time.valid ? <OverviewSkeleton /> : null}
      {initialError && allQueries.every((query) => !query.data) ? <ErrorState error={initialError} onRetry={() => void Promise.all(allQueries.map((query) => query.refetch()))} /> : null}
      {allQueries.some((query) => query.isRefetchError) && allQueries.every((query) => query.data) ? <StaleWarning error={initialError} onRetry={() => void Promise.all(allQueries.map((query) => query.refetch()))} /> : null}
      {widgetData ? <OverviewContent
        data={widgetData}
        layoutLoadError={savedLayout.error}
        layoutLoadedAt={savedLayout.dataUpdatedAt}
        layoutLoading={savedLayout.isPending}
        layoutResponse={savedLayout.data?.data}
        onReloadLayout={async () => { await savedLayout.refetch(); }}
      /> : null}
    </div>
  );
}

function OverviewContent({ data, layoutResponse, layoutLoadError, layoutLoadedAt, layoutLoading, onReloadLayout }: {
  data: OverviewWidgetData;
  layoutResponse: DashboardLayoutResponse | undefined;
  layoutLoadError: unknown;
  layoutLoadedAt: number;
  layoutLoading: boolean;
  onReloadLayout: () => Promise<void>;
}) {
  const { t } = useI18n();
  const editor = useDashboardLayoutEditor(layoutResponse, layoutLoadedAt, t);
  const { width, containerRef, mounted } = useContainerWidth({ initialWidth: 1200 });
  const [draggingWidgetId, setDraggingWidgetId] = useState<string | null>(null);
  const [hideDropActive, setHideDropActive] = useState(false);
  const hideZoneRef = useRef<HTMLElement | null>(null);
  const externalWidgetRef = useRef<string | null>(null);
  const breakpoint: DashboardBreakpoint = width >= DASHBOARD_BREAKPOINTS.lg ? "lg" : "md";
  const desktopEditing = editor.isEditing && breakpoint === "lg";
  const finishEditing = editor.finishEditing;
  useEffect(() => {
    if (breakpoint === "md" && editor.isEditing) finishEditing();
  }, [breakpoint, editor.isEditing, finishEditing]);
  const layouts = useMemo<ResponsiveLayouts<DashboardBreakpoint>>(() => ({
    lg: desktopGridLayout(editor.draft, desktopEditing),
    md: tabletGridLayout(editor.draft),
  }), [desktopEditing, editor.draft]);
  const activeLayout = layouts[breakpoint] ?? layouts.lg ?? [];
  const hiddenWidgets = editor.draft.filter((item) => item.hidden);
  const hiddenTrayHint = breakpoint === "md"
    ? (hiddenWidgets.length ? t("dashboardLayout.hiddenTablet") : t("dashboardLayout.arrangementDesktop"))
    : (draggingWidgetId ? t("dashboardLayout.dropHide") : hiddenWidgets.length ? t("dashboardLayout.hiddenCount", { count: hiddenWidgets.length }) : t("dashboardLayout.dragHide"));
  const canStartEditing = breakpoint === "lg" && !layoutLoading && !layoutLoadError;
  const editorHint = editor.isEditing
    ? (breakpoint === "lg" ? t("dashboardLayout.editHintDesktop") : t("dashboardLayout.tabletGenerated"))
    : layoutLoading
      ? t("dashboardLayout.loading")
      : breakpoint === "md"
        ? t("dashboardLayout.tabletSaved")
        : t("dashboardLayout.idleHint");
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
      <section className={`dashboard-editor-bar ${editor.isEditing ? "editing" : ""}`} aria-label={t("dashboardLayout.controlsAria")}>
        <div>
          <strong>{editor.isEditing ? t("dashboardLayout.editing") : t("dashboardLayout.layout")}</strong>
          <span>{editorHint}</span>
        </div>
        <div className="dashboard-editor-actions">
          {editor.isEditing ? <>
            <button className="button ghost dashboard-editor-only" disabled={editor.saveStatus === "saving"} onClick={editor.cancelEditing} type="button"><X aria-hidden="true" size={15} />{t("dashboardLayout.cancel")}</button>
            <button className="button ghost dashboard-editor-only" disabled={editor.saveStatus === "saving"} onClick={() => void editor.resetLayout()} type="button"><RotateCcw aria-hidden="true" size={15} />{t("dashboardLayout.resetDefault")}</button>
            <button className="button dashboard-editor-only" disabled={editor.saveStatus === "saving"} onClick={() => void editor.saveNow()} type="button"><Save aria-hidden="true" size={15} />{t("dashboardLayout.save")}</button>
            <button className="button primary dashboard-editor-only" onClick={editor.finishEditing} type="button">{t("dashboardLayout.done")}</button>
          </> : <button className="button dashboard-edit-button" disabled={!canStartEditing} onClick={editor.startEditing} type="button"><Settings2 aria-hidden="true" size={15} />{t("dashboardLayout.edit")}</button>}
        </div>
      </section>
      {layoutLoadError ? <div className="dashboard-layout-message error" role="alert"><span>{t("dashboardLayout.loadError")}</span><button className="button ghost" onClick={() => void onReloadLayout()} type="button"><RefreshCw aria-hidden="true" size={15} />{t("dashboardLayout.reload")}</button></div> : null}
      {editor.conflict ? <div className="dashboard-layout-message conflict" role="alert"><span>{t("dashboardLayout.conflict")}</span><button className="button" onClick={() => void editor.reload(onReloadLayout)} type="button"><RefreshCw aria-hidden="true" size={15} />{t("dashboardLayout.reloadLatest")}</button></div> : null}
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
          key={`${breakpoint}:${layoutLoadedAt}:${visibleWidgetKey}`}
          breakpoints={DASHBOARD_BREAKPOINTS}
          className={`dashboard-grid ${desktopEditing ? "is-editing" : ""}`}
          cols={DASHBOARD_COLUMNS}
          compactor={verticalCompactor}
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
) {
  const [draft, setDraftState] = useState<DashboardWidgetLayout[]>(createDefaultOverviewLayout);
  const [isEditing, setIsEditing] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [conflict, setConflict] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const draftRef = useRef(draft);
  const committedRef = useRef(draft);
  const revisionRef = useRef(0);
  const editBaselineRef = useRef(draft);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savingRef = useRef(false);
  const queuedRef = useRef<DashboardWidgetLayout[] | null>(null);
  const persistRef = useRef<(candidate: DashboardWidgetLayout[]) => Promise<void>>(async () => undefined);
  const layoutResponseRef = useRef(layoutResponse);
  layoutResponseRef.current = layoutResponse;

  const setDraft = useCallback((next: DashboardWidgetLayout[]) => {
    draftRef.current = next;
    setDraftState(next);
  }, []);

  useEffect(() => {
    const response = layoutResponseRef.current;
    if (!response || layoutLoadedAt === 0) return;
    const merged = normalizeOverviewLayout(response.widgets);
    revisionRef.current = response.revision;
    committedRef.current = merged;
    editBaselineRef.current = merged;
    setDraft(merged);
    setConflict(false);
    setErrorMessage(null);
    setSaveStatus("idle");
  }, [layoutLoadedAt, setDraft]);

  const persistNow = useCallback(async (candidate: DashboardWidgetLayout[]) => {
    const normalized = normalizeOverviewLayout(candidate);
    if (savingRef.current) {
      queuedRef.current = normalized;
      return;
    }
    savingRef.current = true;
    setSaveStatus("saving");
    setErrorMessage(null);
    try {
      const response = await api.saveDashboardLayout(OVERVIEW_DASHBOARD_KEY, {
        layoutVersion: OVERVIEW_LAYOUT_VERSION,
        revision: revisionRef.current,
        widgets: normalized,
      });
      const saved = normalizeOverviewLayout(response.data.widgets);
      revisionRef.current = response.data.revision;
      committedRef.current = saved;
      if (!queuedRef.current) setDraft(saved);
      setSaveStatus("saved");
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
    } finally {
      savingRef.current = false;
      const queued = queuedRef.current;
      queuedRef.current = null;
      if (queued) void persistRef.current(queued);
    }
  }, [setDraft, t]);

  useEffect(() => { persistRef.current = persistNow; }, [persistNow]);
  useEffect(() => () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current); }, []);

  const queueSave = useCallback((next: DashboardWidgetLayout[]) => {
    setDraft(next);
    setSaveStatus("unsaved");
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => { void persistRef.current(next); }, 650);
  }, [setDraft]);

  const saveNow = useCallback(async () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = null;
    await persistRef.current(draftRef.current);
  }, []);

  const finishEditing = useCallback(() => {
    void saveNow();
    setIsEditing(false);
  }, [saveNow]);

  return {
    draft,
    isEditing,
    saveStatus,
    conflict,
    errorMessage,
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
      if (!layoutsEqual(baseline, committedRef.current)) void persistRef.current(baseline);
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
