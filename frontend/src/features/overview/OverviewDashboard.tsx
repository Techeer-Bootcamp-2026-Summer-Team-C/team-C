import { Activity, BellRing, CircleAlert, MonitorDot, ShieldAlert, Siren } from "lucide-react";
import { lazy, Suspense } from "react";
import { DetectionActivityTable } from "../../components/charts";
import { ChartFrame, EdrStateSummary, ErrorState, KpiCard, Panel, Skeleton, StaleWarning } from "../../components/ui";
import type { DashboardSummaryDto, EndpointDto, EndpointSummaryDto, IncidentDto, TimeRangeQuery } from "../../contracts";
import { useI18n } from "../../i18n/LocaleContext";
import { AlertSeverityDonut } from "./AlertSeverityDonut";
import { IncidentQueueList, RiskEndpointRanking } from "./InvestigationQueues";
import { OVERVIEW_WIDGET_TYPES, type OverviewWidgetType } from "../overviewLayout/overviewLayoutModel";

const DetectionActivityPanel = lazy(() => import("./DetectionActivityPanel"));

export const OVERVIEW_BLOCK_IDS = OVERVIEW_WIDGET_TYPES;

export interface OverviewDashboardData {
  dashboard: DashboardSummaryDto | undefined;
  endpoints: EndpointSummaryDto | undefined;
  topEndpoints: EndpointDto[];
  incidentQueue: IncidentDto[];
  selectedEndpointId: number | undefined;
  timeRange: TimeRangeQuery;
}

export interface OverviewPanelState {
  pending: boolean;
  error: unknown;
  stale: boolean;
  onRetry: () => void;
}

const IDLE_PANEL_STATE: OverviewPanelState = { pending: false, error: null, stale: false, onRetry: () => undefined };
const IDLE_SUMMARY_STATE = { dashboard: IDLE_PANEL_STATE, endpoints: IDLE_PANEL_STATE };

export interface OverviewDashboardProps {
  data: OverviewDashboardData;
  queueState?: { endpoints: OverviewPanelState; incidents: OverviewPanelState };
  summaryState?: { dashboard: OverviewPanelState; endpoints: OverviewPanelState };
}

export function OverviewDashboard({ data, queueState = { endpoints: IDLE_PANEL_STATE, incidents: IDLE_PANEL_STATE }, summaryState = IDLE_SUMMARY_STATE }: OverviewDashboardProps) {
  const { t } = useI18n();
  return <section aria-label={t("overview.dashboardAria")} className="overview-dashboard">
    <OverviewSignalRibbon data={data} />
    <div className="overview-posture-row">
      <OverviewBlock id="edr-state"><OverviewWidget data={data} queueState={queueState} summaryState={summaryState} type="edr-state" /></OverviewBlock>
    </div>
    <div aria-label={t("overview.kpiAria")} className="overview-kpi-row">
      {(["kpi-alerts", "kpi-critical-alerts", "kpi-high-risk-endpoints", "kpi-open-incidents"] as const).map((type) => <OverviewBlock id={type} key={type}><OverviewWidget data={data} queueState={queueState} summaryState={summaryState} type={type} /></OverviewBlock>)}
    </div>
    <div className="overview-analysis-row">
      {(["detection-activity", "alert-severity"] as const).map((type) => <OverviewBlock id={type} key={type}><OverviewWidget data={data} queueState={queueState} summaryState={summaryState} type={type} /></OverviewBlock>)}
    </div>
    <div className="overview-queue-row">
      {(["highest-risk-endpoints", "incident-queue"] as const).map((type) => <OverviewBlock id={type} key={type}><OverviewWidget data={data} queueState={queueState} summaryState={summaryState} type={type} /></OverviewBlock>)}
    </div>
  </section>;
}

export function OverviewWidget({ data, queueState = { endpoints: IDLE_PANEL_STATE, incidents: IDLE_PANEL_STATE }, summaryState = IDLE_SUMMARY_STATE, type }: OverviewDashboardProps & { type: OverviewWidgetType }) {
  const { t } = useI18n();
  if (type === "edr-state") return <ResourceFeedback data={data.dashboard} render={(dashboard) => <EdrStateSummary state={dashboard.edrState} />} rows={3} state={summaryState.dashboard} />;
  if (type === "kpi-alerts") return <ResourceFeedback data={data.dashboard} render={(dashboard) => <KpiCard detail={t("overview.alertsDetail")} icon={<BellRing size={18} />} label={t("overview.totalAlerts")} to={timeScopedPath("/alerts", data.timeRange, data.selectedEndpointId)} tone="accent" value={dashboard.alerts.totalCount} />} rows={2} state={summaryState.dashboard} />;
  if (type === "kpi-critical-alerts") return <ResourceFeedback data={data.dashboard} render={(dashboard) => {
    const criticalAlerts = dashboard.alerts.bySeverity.find((row) => row.severity === "CRITICAL")?.count ?? 0;
    return <KpiCard detail={t("overview.criticalAlertsDetail")} icon={<Siren size={18} />} label={t("overview.criticalAlerts")} to={timeScopedPath("/alerts?severity=CRITICAL", data.timeRange, data.selectedEndpointId)} tone={criticalAlerts ? "critical" : "neutral"} value={criticalAlerts} />;
  }} rows={2} state={summaryState.dashboard} />;
  if (type === "kpi-high-risk-endpoints") return <ResourceFeedback data={data.endpoints} render={(endpoints) => <KpiCard detail={t("overview.highRiskEndpointsDetail")} icon={<ShieldAlert size={18} />} label={t("overview.highRiskEndpoints")} to={scopedPath("/endpoints?riskLevel=HIGH&sortBy=riskScore&sortOrder=desc", data.selectedEndpointId, "endpointIds")} tone={endpoints.risk.highRiskEndpointCount ? "high" : "neutral"} value={endpoints.risk.highRiskEndpointCount} />} rows={2} state={summaryState.endpoints} />;
  if (type === "kpi-open-incidents") return <ResourceFeedback data={data.dashboard} render={(dashboard) => <KpiCard detail={t("overview.currentlyOpen")} icon={<CircleAlert size={18} />} label={t("overview.openIncidents")} to={timeScopedPath("/incidents?status=OPEN", data.timeRange, data.selectedEndpointId)} tone={dashboard.incidents.openCount ? "info" : "neutral"} value={dashboard.incidents.openCount} />} rows={2} state={summaryState.dashboard} />;
  if (type === "detection-activity") return <ResourceFeedback data={data.dashboard} render={(dashboard) => <ChartFrame description={t("overview.detectionActivityDescription")} fallback={<DetectionActivityTable alerts={dashboard.alerts.timeSeries} events={dashboard.events.timeSeries} incidents={dashboard.incidents.timeSeries} />} title={t("overview.detectionActivity")}><Suspense fallback={<Skeleton rows={4} />}><DetectionActivityPanel alerts={dashboard.alerts.timeSeries} events={dashboard.events.timeSeries} incidents={dashboard.incidents.timeSeries} /></Suspense></ChartFrame>} rows={5} state={summaryState.dashboard} />;
  if (type === "alert-severity") return <ResourceFeedback data={data.dashboard} render={(dashboard) => <Panel title={t("overview.alertSeverity")} subtitle={t("overview.serverDistribution")}><AlertSeverityDonut label={t("overview.totalAlerts")} rows={dashboard.alerts.bySeverity} total={dashboard.alerts.totalCount} /></Panel>} rows={5} state={summaryState.dashboard} />;
  if (type === "highest-risk-endpoints") return <Panel title={t("overview.highestRiskEndpoints")} subtitle={t("overview.currentRiskSnapshot")}><QueueFeedback items={data.topEndpoints} render={(items) => <RiskEndpointRanking endpoints={items} />} state={queueState.endpoints} /></Panel>;
  return <Panel title={t("overview.incidentQueueWidget")} subtitle={t("overview.recentOpenIncidents")}><QueueFeedback items={data.incidentQueue} render={(items) => <IncidentQueueList incidents={items} />} state={queueState.incidents} /></Panel>;
}

export function OverviewSignalRibbon({ data }: { data: OverviewDashboardData }) {
  if (!data.dashboard || !data.endpoints) return null;
  return <SignalRibbon dashboard={data.dashboard} endpoints={data.endpoints} />;
}

function SignalRibbon({ dashboard, endpoints }: { dashboard: DashboardSummaryDto; endpoints: EndpointSummaryDto }) {
  const { t } = useI18n();
  const signals = [
    { icon: <Activity aria-hidden="true" size={16} />, label: t("overview.signalEvents"), value: dashboard.events.totalCount, tone: "events" },
    { icon: <Siren aria-hidden="true" size={16} />, label: t("overview.signalDetections"), value: dashboard.alerts.totalCount, tone: "alerts" },
    { icon: <MonitorDot aria-hidden="true" size={16} />, label: t("overview.signalEndpointReach"), value: `${endpoints.onlineCount} / ${endpoints.totalCount}`, tone: "endpoints" },
    { icon: <ShieldAlert aria-hidden="true" size={16} />, label: t("overview.signalOpenCases"), value: dashboard.incidents.openCount, tone: "incidents" },
  ] as const;
  return <section aria-label={t("overview.signalRibbon")} className="overview-signal-ribbon">
    <header><span aria-hidden="true" /><strong>{t("overview.signalRibbon")}</strong><small>{t("overview.backendSnapshot")}</small></header>
    <div>{signals.map((signal) => <article className={`signal-${signal.tone}`} key={signal.label}>
      {signal.icon}<span>{signal.label}</span><strong>{signal.value}</strong>
    </article>)}</div>
  </section>;
}

function ResourceFeedback<Item>({ data, render, rows, state }: {
  data: Item | undefined;
  render: (data: Item) => React.ReactNode;
  rows: number;
  state: OverviewPanelState;
}) {
  if (data !== undefined) return <>{render(data)}</>;
  if (state.error) return <ErrorState error={state.error} onRetry={state.onRetry} />;
  return <Skeleton rows={rows} />;
}

function QueueFeedback<Item>({ items, render, state }: { items: Item[]; render: (items: Item[]) => React.ReactNode; state: OverviewPanelState }) {
  if (state.pending && !items.length) return <Skeleton rows={5} />;
  if (state.error && !items.length) return <ErrorState error={state.error} onRetry={state.onRetry} />;
  return <>{state.stale && items.length ? <StaleWarning error={state.error} onRetry={state.onRetry} /> : null}{render(items)}</>;
}

function OverviewBlock({ id, children }: { id: typeof OVERVIEW_BLOCK_IDS[number]; children: React.ReactNode }) {
  return <div className="overview-block" data-overview-block={id}>{children}</div>;
}

function scopedPath(path: string, endpointId: number | undefined, parameter = "endpointId"): string {
  if (endpointId === undefined) return path;
  return `${path}${path.includes("?") ? "&" : "?"}${parameter}=${endpointId}`;
}

function timeScopedPath(path: string, timeRange: TimeRangeQuery, endpointId: number | undefined): string {
  const [pathname, rawQuery = ""] = path.split("?");
  const params = new URLSearchParams(rawQuery);
  if (timeRange.timePreset) params.set("timePreset", timeRange.timePreset);
  if (timeRange.timePreset === "CUSTOM") {
    if (timeRange.from) params.set("from", timeRange.from);
    if (timeRange.to) params.set("to", timeRange.to);
  } else {
    params.delete("from");
    params.delete("to");
  }
  if (endpointId !== undefined) params.set("endpointId", String(endpointId));
  const query = params.toString();
  return query ? `${pathname}?${query}` : pathname ?? path;
}
