import {
  Activity,
  BellRing,
  ChartPie,
  CircleAlert,
  CircleCheck,
  GripVertical,
  LayoutDashboard,
  ListFilter,
  ListOrdered,
  MonitorDot,
  Pencil,
  Plus,
  ShieldCheck,
  Siren,
  Trash2,
  X,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useId, useMemo, useRef, useState, useSyncExternalStore, type DragEvent as ReactDragEvent, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Link } from "react-router-dom";
import {
  ResponsiveGridLayout,
  getCompactor,
  useContainerWidth,
  type Layout,
  type LayoutItem,
  type ResponsiveLayouts,
} from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import { Button, Dialog, SelectField, TextField } from "../../components/primitives";
import {
  OverviewDashboard,
  OVERVIEW_BLOCK_IDS,
  OverviewSignalRibbon,
  OverviewWidget,
  type OverviewDashboardProps,
} from "../overview/OverviewDashboard";
import { useI18n } from "../../i18n/LocaleContext";
import { useOverviewLayout } from "./OverviewLayoutContext";
import {
  DEFAULT_DASHBOARD_ID,
  OVERVIEW_GRID_COLUMNS,
  OVERVIEW_GRID_MAX_ROWS,
  OVERVIEW_WIDGET_DEFINITIONS,
  createOverviewWidget,
  findAvailableOverviewWidgetPosition,
  overviewWidgetsOverlap,
  widgetDefinition,
  type CustomDashboardWidget,
  type CustomOverviewDashboard,
  type OverviewWidgetType,
} from "./overviewLayoutModel";

const WIDGET_DRAG_TYPE = "application/x-edr-overview-widget";
const FIXED_GRID_COMPACTOR = getCompactor(null, false, true);
const WIDGET_CATALOG_ICONS: Record<OverviewWidgetType, LucideIcon> = {
  "edr-state": ShieldCheck,
  "kpi-alerts": BellRing,
  "kpi-critical-alerts": Siren,
  "kpi-high-risk-endpoints": MonitorDot,
  "kpi-open-incidents": CircleAlert,
  "detection-activity": Activity,
  "alert-severity": ChartPie,
  "highest-risk-endpoints": ListOrdered,
  "incident-queue": ListFilter,
};
type DesktopBreakpoint = "desktop";
type PlacementIssue = "duplicate" | "space";
type BuilderFocusTarget = { kind: "palette"; type: OverviewWidgetType } | { kind: "widget"; uid: string };

interface BuilderState {
  dashboardId: string | null;
  name: string;
  widgets: CustomDashboardWidget[];
}

export function OverviewDashboardWorkspace({ mode = "overview", onSettingsClose = () => undefined, settingsOpen = false, ...props }: OverviewDashboardProps & {
  mode?: "overview" | "manage";
  onSettingsClose?: () => void;
  settingsOpen?: boolean;
}) {
  const { t } = useI18n();
  const layout = useOverviewLayout();
  const editingAvailable = useDesktopDashboardEditing();
  const [builder, setBuilder] = useState<BuilderState | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CustomOverviewDashboard | null>(null);
  const activeDashboard = layout.activeDashboard;
  const managementMode = mode === "manage";
  const managerLocked = builder !== null;

  function openNewDashboard(): void {
    if (!editingAvailable) return;
    setBuilder({ dashboardId: null, name: "", widgets: [] });
    onSettingsClose();
  }

  function openExistingDashboard(): void {
    if (!editingAvailable || !activeDashboard) return;
    setBuilder({ dashboardId: activeDashboard.id, name: activeDashboard.name, widgets: activeDashboard.widgets.map((widget) => ({ ...widget })) });
    onSettingsClose();
  }

  return <div className={`overview-dashboard-workspace ${managementMode ? "dashboard-workbench" : "dashboard-overview-view"}`}>
    {managementMode && !builder ? <header className="dashboard-layout-identity">
      <span className="eyebrow">{t("dashboard.activeLayout")}</span>
      <h2>{activeDashboard?.name ?? t("dashboard.defaultName")}</h2>
      <p>{t("dashboard.managementHint")}</p>
    </header> : null}

    {managementMode && builder ? <DashboardBuilder
      builder={builder}
      editingAvailable={editingAvailable}
      onCancel={() => setBuilder(null)}
      onChange={setBuilder}
      onSave={() => {
        if (!editingAvailable) return;
        const name = builder.name.trim();
        if (!name || !builder.widgets.length) return;
        if (builder.dashboardId) layout.updateDashboard(builder.dashboardId, name, builder.widgets);
        else layout.createDashboard(name, builder.widgets);
        setBuilder(null);
      }}
      props={props}
    /> : managementMode ? <DashboardManagementHome
      activeDashboard={activeDashboard}
      activeDashboardId={layout.activeDashboardId}
      dashboards={layout.dashboards}
      editingAvailable={editingAvailable}
      hideActions={settingsOpen}
      onEdit={openExistingDashboard}
      onNew={openNewDashboard}
      onSelect={layout.selectDashboard}
      props={props}
    /> : activeDashboard ? <>
      <header className="dashboard-applied-layout">
        <div><span className="eyebrow">{t("dashboard.activeLayout")}</span><strong>{activeDashboard.name}</strong><p>{t("dashboard.activeCustomDescription")}</p></div>
        <Button onClick={() => layout.selectDashboard(DEFAULT_DASHBOARD_ID)} type="button" variant="ghost">{t("dashboard.restoreDefault")}</Button>
      </header>
      <CustomDashboardView dashboard={activeDashboard} desktopLayout={editingAvailable} props={props} />
    </> : <OverviewDashboard {...props} />}

    {managementMode ? <Dialog
      closeLabel={t("dashboard.closeSettings")}
      eyebrow="LAYOUT SETTINGS"
      onClose={onSettingsClose}
      open={settingsOpen}
      title={t("dashboard.settingsTitle")}
    >
      <div className="dashboard-settings-content">
        <p>{t("dashboard.settingsDescription")}</p>
        <SelectField
          className="dashboard-selector"
          disabled={managerLocked}
          label={t("dashboard.selectorLabel")}
          onChange={(event) => {
            layout.selectDashboard(event.target.value);
            setBuilder(null);
          }}
          value={layout.activeDashboardId}
        >
          <option value={DEFAULT_DASHBOARD_ID}>{t("dashboard.defaultName")}</option>
          {layout.dashboards.map((dashboard) => <option key={dashboard.id} value={dashboard.id}>{dashboard.name}</option>)}
        </SelectField>
        <small>{t("dashboard.savedCount", { count: layout.dashboards.length })}</small>
        <div className="dashboard-settings-actions">
          <Button disabled={!editingAvailable || managerLocked} onClick={openNewDashboard} type="button"><Plus aria-hidden="true" size={16} />{t("dashboard.new")}</Button>
          {activeDashboard ? <>
            <Button disabled={!editingAvailable || managerLocked} onClick={openExistingDashboard} type="button" variant="ghost"><Pencil aria-hidden="true" size={16} />{t("dashboard.edit")}</Button>
            <Button disabled={!editingAvailable || managerLocked} onClick={() => {
              onSettingsClose();
              setDeleteTarget(activeDashboard);
            }} type="button" variant="ghost"><Trash2 aria-hidden="true" size={16} />{t("dashboard.delete")}</Button>
          </> : null}
        </div>
        {!editingAvailable ? <p className="dashboard-edit-unavailable">{t("dashboard.editUnavailable")}</p> : null}
      </div>
    </Dialog> : null}

    {managementMode ? <Dialog
      actions={<>
        <Button onClick={() => setDeleteTarget(null)} type="button" variant="ghost">{t("dashboard.cancel")}</Button>
        <Button disabled={!editingAvailable} onClick={() => {
          if (deleteTarget && editingAvailable) {
            layout.deleteDashboard(deleteTarget.id);
            if (builder?.dashboardId === deleteTarget.id) setBuilder(null);
          }
          setDeleteTarget(null);
        }} type="button" variant="danger">{t("dashboard.confirmDelete")}</Button>
      </>}
      closeLabel={t("dashboard.closeDelete")}
      eyebrow="CUSTOM DASHBOARD"
      onClose={() => setDeleteTarget(null)}
      open={deleteTarget !== null}
      title={t("dashboard.deleteTitle")}
    >
      <p>{t("dashboard.deleteDescription", { name: deleteTarget?.name ?? "" })}</p>
    </Dialog> : null}
  </div>;
}

function DashboardManagementHome({ activeDashboard, activeDashboardId, dashboards, editingAvailable, hideActions, onEdit, onNew, onSelect, props }: {
  activeDashboard: CustomOverviewDashboard | null;
  activeDashboardId: string;
  dashboards: CustomOverviewDashboard[];
  editingAvailable: boolean;
  hideActions: boolean;
  onEdit: () => void;
  onNew: () => void;
  onSelect: (dashboardId: string) => void;
  props: OverviewDashboardProps;
}) {
  const { t } = useI18n();
  const widgetCount = activeDashboard?.widgets.length ?? OVERVIEW_BLOCK_IDS.length;
  return <section aria-label={t("dashboard.managerAria")} className="dashboard-management-home">
    <aside className="dashboard-management-catalog">
      <header><span>{t("dashboard.selectorLabel")}</span><strong>{t("dashboard.layoutCatalog")}</strong></header>
      <button aria-pressed={activeDashboardId === DEFAULT_DASHBOARD_ID} className={activeDashboardId === DEFAULT_DASHBOARD_ID ? "active" : undefined} onClick={() => onSelect(DEFAULT_DASHBOARD_ID)} type="button"><span><strong>{t("dashboard.defaultName")}</strong><small>{t("dashboard.defaultFixed")}</small></span><small>{OVERVIEW_BLOCK_IDS.length}</small></button>
      {dashboards.map((dashboard) => <button aria-pressed={activeDashboardId === dashboard.id} className={activeDashboardId === dashboard.id ? "active" : undefined} key={dashboard.id} onClick={() => onSelect(dashboard.id)} type="button"><span><strong>{dashboard.name}</strong><small>{t("dashboard.browserLocal")}</small></span><small>{dashboard.widgets.length}</small></button>)}
    </aside>
    <div className="dashboard-management-summary">
      <header><div><span className="eyebrow">{activeDashboard ? t("dashboard.workbenchContext") : t("dashboard.overviewContext")}</span><h3>{activeDashboard?.name ?? t("dashboard.defaultName")}</h3></div>{!hideActions ? <div className="dashboard-management-actions"><Button disabled={!editingAvailable} onClick={onNew} type="button"><Plus aria-hidden="true" size={16} />{t("dashboard.new")}</Button>{activeDashboard ? <Button disabled={!editingAvailable} onClick={onEdit} type="button" variant="ghost"><Pencil aria-hidden="true" size={16} />{t("dashboard.edit")}</Button> : null}</div> : null}</header>
      <p>{activeDashboard ? t("dashboard.builderDescription") : t("dashboard.readOnlyHint")}</p>
      <dl><div><dt>{t("dashboard.layoutState")}</dt><dd>{activeDashboard ? t("dashboard.savedLayout") : t("dashboard.defaultFixed")}</dd></div><div><dt>{t("dashboard.widgetCount")}</dt><dd>{widgetCount}</dd></div><div><dt>{t("dashboard.storage")}</dt><dd>{activeDashboard ? t("dashboard.browserLocal") : t("dashboard.productDefault")}</dd></div></dl>
      <div className="dashboard-management-next"><div><strong>{activeDashboard ? t("dashboard.editTitle") : t("dashboard.defaultName")}</strong><span>{activeDashboard ? t("dashboard.managementHint") : t("dashboard.defaultRouteHint")}</span></div>{activeDashboard ? <Button disabled={!editingAvailable || hideActions} onClick={onEdit} type="button" variant="primary">{t("dashboard.openDraft")}</Button> : <Link className="button primary" to="/">{t("dashboard.openOverview")}</Link>}</div>
      {!editingAvailable && !hideActions ? <p className="dashboard-edit-unavailable">{t("dashboard.editUnavailable")}</p> : null}
    </div>
    {activeDashboard ? <div className="dashboard-management-preview"><CustomDashboardView dashboard={activeDashboard} desktopLayout={editingAvailable} props={props} /></div> : null}
  </section>;
}

function DashboardBuilder({ builder, editingAvailable, onCancel, onChange, onSave, props }: {
  builder: BuilderState;
  editingAvailable: boolean;
  onCancel: () => void;
  onChange: (builder: BuilderState) => void;
  onSave: () => void;
  props: OverviewDashboardProps;
}) {
  const { t } = useI18n();
  const [draggedType, setDraggedType] = useState<OverviewWidgetType | null>(null);
  const [placementIssue, setPlacementIssue] = useState<PlacementIssue | null>(null);
  const pendingFocusRef = useRef<BuilderFocusTarget | null>(null);
  const valid = Boolean(builder.name.trim()) && builder.widgets.length > 0;
  const usedTypes = new Set(builder.widgets.map((widget) => widget.type));
  const availableDefinitions = OVERVIEW_WIDGET_DEFINITIONS.filter((definition) => !usedTypes.has(definition.type));
  const registerPaletteButton = useCallback((type: OverviewWidgetType, element: HTMLButtonElement | null) => {
    if (element && pendingFocusRef.current?.kind === "palette" && pendingFocusRef.current.type === type) {
      pendingFocusRef.current = null;
      element.focus();
    }
  }, []);
  const registerWidgetHandle = useCallback((uid: string, element: HTMLButtonElement | null) => {
    if (element && pendingFocusRef.current?.kind === "widget" && pendingFocusRef.current.uid === uid) {
      pendingFocusRef.current = null;
      element.focus();
    }
  }, []);

  function addWidget(type: OverviewWidgetType, position?: Pick<CustomDashboardWidget, "x" | "y" | "w" | "h">): void {
    if (!editingAvailable) return;
    setDraggedType(null);
    if (builder.widgets.some((widget) => widget.type === type)) {
      setPlacementIssue("duplicate");
      return;
    }
    const widgets = position
      ? applyDroppedWidget(builder.widgets, type, position)
      : tryAddOverviewWidget(builder.widgets, type);
    if (widgets === builder.widgets) {
      setPlacementIssue("space");
      return;
    }
    setPlacementIssue(null);
    const addedWidget = widgets[widgets.length - 1];
    if (addedWidget) pendingFocusRef.current = { kind: "widget", uid: addedWidget.uid };
    onChange({ ...builder, widgets });
  }

  return <section aria-label={builder.dashboardId ? t("dashboard.editTitle") : t("dashboard.newTitle")} className="dashboard-builder">
    <header className="dashboard-builder-header">
      <div><span className="eyebrow">CUSTOM OVERVIEW</span><h2>{builder.dashboardId ? t("dashboard.editTitle") : t("dashboard.newTitle")}</h2><p>{t("dashboard.builderDescription")}</p></div>
      <div className="dashboard-builder-actions">
        <TextField className="dashboard-builder-name" disabled={!editingAvailable} helper={t("dashboard.saveRequirements")} label={t("dashboard.nameLabel")} maxLength={80} onChange={(event) => onChange({ ...builder, name: event.target.value })} placeholder={t("dashboard.namePlaceholder")} value={builder.name} />
        <div className="dashboard-builder-buttons">
          <Button onClick={onCancel} type="button" variant="ghost">{t("dashboard.cancel")}</Button>
          <Button disabled={!editingAvailable || !valid} onClick={onSave} type="button" variant="primary">{t("dashboard.save")}</Button>
        </div>
      </div>
    </header>
    <div className="dashboard-builder-body">
      <aside aria-label={t("dashboard.palette")} className="dashboard-widget-palette">
        <h3>{t("dashboard.palette")}</h3>
        <p>{t("dashboard.paletteDescription")}</p>
        <ul>{availableDefinitions.map((definition) => {
          const title = t(definition.titleKey);
          const WidgetIcon = WIDGET_CATALOG_ICONS[definition.type];
          return <li key={definition.type}><button
            aria-label={t("dashboard.addWidget", { widget: title })}
            data-widget-type={definition.type}
            disabled={!editingAvailable}
            draggable={editingAvailable}
            onClick={() => addWidget(definition.type)}
            onDragEnd={() => setDraggedType(null)}
            onDragStart={(event) => startPaletteDrag(event, definition.type, setDraggedType)}
            ref={(element) => registerPaletteButton(definition.type, element)}
            type="button"
          >
            <span aria-hidden="true" className="dashboard-widget-palette-icon"><WidgetIcon size={17} strokeWidth={1.7} /></span>
            <span className="dashboard-widget-palette-copy"><strong>{title}</strong><small>{definition.defaultW} × {definition.defaultH}</small></span>
          </button></li>;
        })}{availableDefinitions.length === 0 ? <li className="dashboard-widget-palette-complete" role="status">
          <CircleCheck aria-hidden="true" size={18} />
          <span>{t("dashboard.paletteComplete")}</span>
        </li> : null}</ul>
      </aside>
      <div className="dashboard-builder-canvas">
        <OverviewSignalRibbon data={props.data} />
        {placementIssue ? <p className="dashboard-placement-unavailable" role="status">{t(placementIssue === "duplicate" ? "dashboard.widgetAlreadyAdded" : "dashboard.widgetPlacementUnavailable")}</p> : null}
        <DashboardGrid
          desktopLayout={editingAvailable}
          draggedType={draggedType}
          editable={editingAvailable}
          onHandleRef={registerWidgetHandle}
          onDropWidget={(type, position) => addWidget(type, position)}
          onRemove={(uid) => {
            const removedWidget = builder.widgets.find((widget) => widget.uid === uid);
            if (removedWidget) pendingFocusRef.current = { kind: "palette", type: removedWidget.type };
            setPlacementIssue(null);
            onChange({ ...builder, widgets: builder.widgets.filter((widget) => widget.uid !== uid) });
          }}
          onWidgetsChange={(widgets) => {
            setPlacementIssue(null);
            onChange({ ...builder, widgets });
          }}
          props={props}
          showEmptyState
          widgets={builder.widgets}
        />
      </div>
    </div>
  </section>;
}

function CustomDashboardView({ dashboard, desktopLayout, props }: { dashboard: CustomOverviewDashboard; desktopLayout: boolean; props: OverviewDashboardProps }) {
  const { t } = useI18n();
  return <section aria-label={t("dashboard.customAria", { name: dashboard.name })} className="custom-dashboard-view">
    <OverviewSignalRibbon data={props.data} />
    <DashboardGrid
      desktopLayout={desktopLayout}
      editable={false}
      props={props}
      widgets={dashboard.widgets}
    />
  </section>;
}

function DashboardGrid({ desktopLayout = true, draggedType = null, editable, onDropWidget, onHandleRef, onRemove, onWidgetsChange, props, showEmptyState = false, widgets }: {
  desktopLayout?: boolean;
  draggedType?: OverviewWidgetType | null;
  editable: boolean;
  onDropWidget?: (type: OverviewWidgetType, position: Pick<CustomDashboardWidget, "x" | "y" | "w" | "h">) => void;
  onHandleRef?: (uid: string, element: HTMLButtonElement | null) => void;
  onRemove?: (uid: string) => void;
  onWidgetsChange?: (widgets: CustomDashboardWidget[]) => void;
  props: OverviewDashboardProps;
  showEmptyState?: boolean;
  widgets: CustomDashboardWidget[];
}) {
  const { t } = useI18n();
  const keyboardInstructionsId = useId();
  const { containerRef, mounted, width } = useContainerWidth({ initialWidth: 1280 });
  const gridLayout = useMemo<Layout>(() => widgets.map(toLayoutItem), [widgets]);
  const layouts = useMemo<ResponsiveLayouts<DesktopBreakpoint>>(() => ({ desktop: gridLayout }), [gridLayout]);

  function commitLayout(nextLayout: Layout): void {
    if (editable && onWidgetsChange) onWidgetsChange(applyGridLayout(widgets, nextLayout));
  }

  const children = widgets.map((widget) => {
    const title = t(widgetDefinition(widget.type).titleKey);
    const geometry = t("dashboard.widgetGeometry", { widget: title, column: widget.x + 1, row: widget.y + 1, width: widget.w, height: widget.h });
    return <article className="custom-dashboard-widget" data-widget-type={widget.type} key={widget.uid}>
      <header className="custom-dashboard-widget-header">
        <button
          aria-describedby={editable ? keyboardInstructionsId : undefined}
          aria-keyshortcuts={editable ? "ArrowLeft ArrowRight ArrowUp ArrowDown Shift+ArrowLeft Shift+ArrowRight Shift+ArrowUp Shift+ArrowDown" : undefined}
          aria-label={`${t("dashboard.dragHandle", { widget: title })}. ${geometry}`}
          className="custom-widget-drag-handle"
          disabled={!editable}
          onKeyDown={editable && onWidgetsChange ? (event) => handleWidgetKeyboardAdjustment(event, widgets, widget.uid, onWidgetsChange) : undefined}
          ref={(element) => onHandleRef?.(widget.uid, element)}
          title={t("dashboard.dragHandle", { widget: title })}
          type="button"
        ><GripVertical aria-hidden="true" size={15} /><span>{title}</span></button>
        {editable && onRemove ? <button aria-label={t("dashboard.removeWidget", { widget: title })} className="custom-widget-remove" onClick={() => onRemove(widget.uid)} title={t("dashboard.removeWidget", { widget: title })} type="button"><X aria-hidden="true" size={15} /></button> : null}
      </header>
      <div className="custom-dashboard-widget-body"><OverviewWidget {...props} type={widget.type} /></div>
    </article>;
  });

  const keyboardInstructions = <span className="sr-only" id={keyboardInstructionsId}>{t("dashboard.keyboardInstructions")}</span>;

  if (!desktopLayout) return <div className="custom-dashboard-static-grid" data-dashboard-editing="disabled">{keyboardInstructions}{children}</div>;

  return <div className={`custom-dashboard-grid-container${showEmptyState && !widgets.length ? " is-empty" : ""}`} data-dashboard-editing={editable ? "enabled" : "disabled"} ref={containerRef}>
    {keyboardInstructions}
    {mounted ? <ResponsiveGridLayout<DesktopBreakpoint>
      breakpoints={{ desktop: 0 }}
      cols={{ desktop: OVERVIEW_GRID_COLUMNS }}
      compactor={FIXED_GRID_COMPACTOR}
      containerPadding={[0, 0]}
      dragConfig={{ enabled: editable, bounded: true, handle: ".custom-widget-drag-handle", cancel: "button:not(.custom-widget-drag-handle),a,input,select,textarea", threshold: 3 }}
      dropConfig={{
        enabled: Boolean(editable && draggedType && onDropWidget),
        defaultItem: draggedType ? { w: widgetDefinition(draggedType).defaultW, h: widgetDefinition(draggedType).defaultH } : { w: 3, h: 2 },
        onDragOver: () => draggedType ? { w: widgetDefinition(draggedType).defaultW, h: widgetDefinition(draggedType).defaultH } : false,
      }}
      layouts={layouts}
      margin={[12, 12]}
      maxRows={OVERVIEW_GRID_MAX_ROWS}
      onDragStop={commitLayout}
      onDrop={(_nextLayout, item) => {
        if (!draggedType || !item || !onDropWidget) return;
        onDropWidget(draggedType, { x: item.x, y: item.y, w: item.w, h: item.h });
      }}
      onResizeStop={commitLayout}
      resizeConfig={{ enabled: editable, handles: ["se"] }}
      rowHeight={44}
      width={width}
    >{children}</ResponsiveGridLayout> : null}
    {showEmptyState && !widgets.length ? <div className="dashboard-builder-empty"><LayoutDashboard aria-hidden="true" size={28} /><h3>{t("dashboard.emptyTitle")}</h3><p>{t("dashboard.emptyDescription")}</p></div> : null}
  </div>;
}

export function applyGridLayout(widgets: readonly CustomDashboardWidget[], layout: Layout): CustomDashboardWidget[] {
  const positions = new Map(layout.map((item) => [item.i, item]));
  const normalized = widgets.map((widget) => {
    const item = positions.get(widget.uid);
    return item ? normalizeGridWidget(widget, item) : { ...widget };
  });
  if (widgetsDoNotOverlap(normalized)) return normalized;

  const repaired: CustomDashboardWidget[] = [];
  for (const widget of normalized) {
    const position = findAvailableOverviewWidgetPosition(widget, repaired);
    if (!position) return widgets.map((candidate) => ({ ...candidate }));
    repaired.push({ ...widget, ...position });
  }
  return repaired;
}

export function applyDroppedWidget(
  widgets: CustomDashboardWidget[],
  type: OverviewWidgetType,
  position: Pick<CustomDashboardWidget, "x" | "y" | "w" | "h">,
): CustomDashboardWidget[] {
  if (widgets.some((widget) => widget.type === type)) return widgets;
  const created = createOverviewWidget(type);
  const widget = normalizeGridWidget(created, position);
  const available = findAvailableOverviewWidgetPosition(widget, widgets);
  return available ? [...widgets, { ...widget, ...available }] : widgets;
}

function normalizeGridWidget(widget: CustomDashboardWidget, item: Pick<LayoutItem, "x" | "y" | "w" | "h">): CustomDashboardWidget {
  const definition = widgetDefinition(widget.type);
  const w = clampGridInteger(item.w, definition.minW, Math.min(definition.maxW, OVERVIEW_GRID_COLUMNS), widget.w);
  const h = clampGridInteger(item.h, definition.minH, Math.min(definition.maxH, OVERVIEW_GRID_MAX_ROWS), widget.h);
  const x = clampGridInteger(item.x, 0, OVERVIEW_GRID_COLUMNS - w, widget.x);
  const y = clampGridInteger(item.y, 0, OVERVIEW_GRID_MAX_ROWS - h, widget.y);
  return { ...widget, x, y, w, h };
}

function clampGridInteger(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return Math.min(Math.max(fallback, min), max);
  return Math.min(Math.max(Math.round(value), min), max);
}

function widgetsDoNotOverlap(widgets: readonly CustomDashboardWidget[]): boolean {
  return widgets.every((widget, index) => widgets.slice(index + 1).every((candidate) => !overviewWidgetsOverlap(widget, candidate)));
}

export function tryAddOverviewWidget(widgets: CustomDashboardWidget[], type: OverviewWidgetType): CustomDashboardWidget[] {
  if (widgets.some((widget) => widget.type === type)) return widgets;
  const widget = createOverviewWidget(type);
  const available = findAvailableOverviewWidgetPosition(widget, widgets);
  return available ? [...widgets, { ...widget, ...available }] : widgets;
}

export function applyKeyboardWidgetAdjustment(
  widgets: CustomDashboardWidget[],
  uid: string,
  key: string,
  resize: boolean,
): CustomDashboardWidget[] {
  const widget = widgets.find((candidate) => candidate.uid === uid);
  if (!widget || !isKeyboardAdjustmentKey(key)) return widgets;
  const definition = widgetDefinition(widget.type);
  const adjusted = { ...widget };

  if (resize) {
    if (key === "ArrowLeft") adjusted.w = Math.max(definition.minW, adjusted.w - 1);
    if (key === "ArrowRight") adjusted.w = Math.min(definition.maxW, OVERVIEW_GRID_COLUMNS - adjusted.x, adjusted.w + 1);
    if (key === "ArrowUp") adjusted.h = Math.max(definition.minH, adjusted.h - 1);
    if (key === "ArrowDown") adjusted.h = Math.min(definition.maxH, OVERVIEW_GRID_MAX_ROWS - adjusted.y, adjusted.h + 1);
  } else {
    if (key === "ArrowLeft") adjusted.x = Math.max(0, adjusted.x - 1);
    if (key === "ArrowRight") adjusted.x = Math.min(OVERVIEW_GRID_COLUMNS - adjusted.w, adjusted.x + 1);
    if (key === "ArrowUp") adjusted.y = Math.max(0, adjusted.y - 1);
    if (key === "ArrowDown") adjusted.y = Math.min(OVERVIEW_GRID_MAX_ROWS - adjusted.h, adjusted.y + 1);
  }

  if (adjusted.x === widget.x && adjusted.y === widget.y && adjusted.w === widget.w && adjusted.h === widget.h) return widgets;
  if (widgets.some((candidate) => candidate.uid !== uid && overviewWidgetsOverlap(adjusted, candidate))) return widgets;
  return widgets.map((candidate) => candidate.uid === uid ? adjusted : candidate);
}

function handleWidgetKeyboardAdjustment(
  event: ReactKeyboardEvent<HTMLButtonElement>,
  widgets: CustomDashboardWidget[],
  uid: string,
  onWidgetsChange: (widgets: CustomDashboardWidget[]) => void,
): void {
  if (!isKeyboardAdjustmentKey(event.key)) return;
  event.preventDefault();
  const adjusted = applyKeyboardWidgetAdjustment(widgets, uid, event.key, event.shiftKey);
  if (adjusted !== widgets) onWidgetsChange(adjusted);
}

function isKeyboardAdjustmentKey(key: string): boolean {
  return key === "ArrowLeft" || key === "ArrowRight" || key === "ArrowUp" || key === "ArrowDown";
}

function toLayoutItem(widget: CustomDashboardWidget): LayoutItem {
  const definition = widgetDefinition(widget.type);
  return {
    i: widget.uid,
    x: widget.x,
    y: widget.y,
    w: widget.w,
    h: widget.h,
    minW: definition.minW,
    minH: definition.minH,
    maxW: definition.maxW,
    maxH: definition.maxH,
  };
}

function startPaletteDrag(event: ReactDragEvent<HTMLButtonElement>, type: OverviewWidgetType, setDraggedType: (type: OverviewWidgetType) => void): void {
  setDraggedType(type);
  event.dataTransfer.effectAllowed = "copy";
  event.dataTransfer.setData(WIDGET_DRAG_TYPE, type);
  event.dataTransfer.setData("text/plain", type);
}

function useDesktopDashboardEditing(): boolean {
  return useSyncExternalStore(subscribeDesktopDashboardEditing, desktopDashboardEditingSnapshot, () => true);
}

const DESKTOP_DASHBOARD_EDIT_QUERY = "(min-width: 1280px)";

function desktopDashboardEditingSnapshot(): boolean {
  return window.matchMedia?.(DESKTOP_DASHBOARD_EDIT_QUERY).matches ?? window.innerWidth >= 1280;
}

function subscribeDesktopDashboardEditing(onChange: () => void): () => void {
  const media = window.matchMedia?.(DESKTOP_DASHBOARD_EDIT_QUERY);
  if (!media) {
    window.addEventListener("resize", onChange);
    return () => window.removeEventListener("resize", onChange);
  }
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}
