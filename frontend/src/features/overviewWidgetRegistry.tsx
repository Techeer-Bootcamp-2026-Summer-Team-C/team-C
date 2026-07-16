import { BellRing, Database, ShieldAlert, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { CountBars, DetectionActivityChart, DetectionActivityTable, SeverityDonut } from "../components/charts";
import { ChartFrame, EdrStatePill, EmptyState, KpiCard, Panel, StatusPill } from "../components/ui";
import type { DashboardSummaryDto, EndpointDto, EndpointSummaryDto, IncidentDto, IngestSummaryDto } from "../contracts";
import type { TranslationKey } from "../i18n/translations";
import type { TranslationParams } from "../i18n/types";
import { formatDateTime, humanize } from "../lib/format";
import { OVERVIEW_WIDGET_DEFINITIONS, type OverviewWidgetDefinition, type WidgetDisplayMode } from "./dashboardLayout";

export interface OverviewWidgetData {
  dashboard: DashboardSummaryDto;
  endpoints: EndpointSummaryDto;
  ingest: IngestSummaryDto;
  topEndpoints: EndpointDto[];
  incidentQueue: IncidentDto[];
  selectedEndpointId: number | undefined;
}

export interface OverviewWidgetRegistration extends OverviewWidgetDefinition {
  titleKey: TranslationKey;
  render: (data: OverviewWidgetData, mode: WidgetDisplayMode, t: Translate) => ReactNode;
}

type Translate = (key: TranslationKey, params?: TranslationParams) => string;

const TITLE_KEYS: Record<string, TranslationKey> = {
  "edr-state": "edrState.current",
  "kpi-alerts": "overview.alerts",
  "kpi-open-incidents": "overview.openIncidents",
  "kpi-high-risk-endpoints": "overview.highRiskEndpoints",
  "kpi-event-failures": "overview.eventFailures",
  "detection-activity": "overview.detectionActivity",
  "alert-severity": "overview.alertSeverity",
  "endpoint-risk": "overview.endpointRisk",
  "highest-risk-endpoints": "overview.highestRiskEndpoints",
  "incident-queue": "overview.incidentQueueWidget",
};

const RENDERERS: Record<string, OverviewWidgetRegistration["render"]> = {
  "edr-state": ({ dashboard }) => (
    <EdrStatePill calculatedAt={dashboard.edrState.calculatedAt} reasons={dashboard.edrState.reasonCodes}
      score={dashboard.edrState.score} state={dashboard.edrState.status} />
  ),
  "kpi-alerts": ({ dashboard, selectedEndpointId }, _mode, t) => (
    <KpiCard detail={t("overview.alertsDetail")} icon={<BellRing size={18} />} label={t("overview.alerts")} to={scopedPath("/alerts", selectedEndpointId)}
      tone="warning" value={dashboard.alerts.totalCount} />
  ),
  "kpi-open-incidents": ({ dashboard, selectedEndpointId }, _mode, t) => (
    <KpiCard detail={t("overview.currentlyOpen")} icon={<ShieldCheck size={18} />} label={t("overview.openIncidents")}
      to={scopedPath("/incidents?status=OPEN", selectedEndpointId)} tone="critical" value={dashboard.incidents.openCount} />
  ),
  "kpi-high-risk-endpoints": ({ endpoints, selectedEndpointId }, _mode, t) => (
    <KpiCard detail={t("overview.highRiskEndpointsDetail")} icon={<ShieldAlert size={18} />} label={t("overview.highRiskEndpoints")}
      to={scopedPath("/endpoints?sortBy=riskScore&sortOrder=desc", selectedEndpointId, "endpointIds")} tone={endpoints.risk.highRiskEndpointCount ? "warning" : "neutral"}
      value={endpoints.risk.highRiskEndpointCount} />
  ),
  "kpi-event-failures": ({ dashboard }, _mode, t) => (
    <KpiCard detail={t("overview.currentFailureRows")} icon={<Database size={18} />} label={t("overview.eventFailures")} to="/operations"
      tone={dashboard.eventFailures.totalCount ? "warning" : "neutral"} value={dashboard.eventFailures.totalCount} />
  ),
  "detection-activity": ({ dashboard }, _mode, t) => (
    <ChartFrame
      description={t("overview.detectionActivityDescription")}
      fallback={<DetectionActivityTable alerts={dashboard.alerts.timeSeries} events={dashboard.events.timeSeries} incidents={dashboard.incidents.timeSeries} />}
      title={t("overview.detectionActivity")}
    >
      <DetectionActivityChart alerts={dashboard.alerts.timeSeries} events={dashboard.events.timeSeries} incidents={dashboard.incidents.timeSeries} />
    </ChartFrame>
  ),
  "alert-severity": ({ dashboard }, mode, t) => (
    <Panel title={t("overview.alertSeverity")} subtitle={t("overview.serverDistribution")}>
      <SeverityDonut mode={mode} rows={dashboard.alerts.bySeverity} total={dashboard.alerts.totalCount} />
    </Panel>
  ),
  "endpoint-risk": ({ endpoints }, mode, t) => (
    <Panel title={t("overview.endpointRisk")} subtitle={t("overview.querySnapshot")}
      meta={<span>{t("overview.highest", { value: endpoints.risk.highestScore ?? t("common.none") })}</span>}>
      <CountBars mode={mode} rows={endpoints.risk.byLevel.map((row) => ({
        label: humanize(row.level), count: row.count, tone: row.level.toLowerCase(),
      }))} />
    </Panel>
  ),
  "highest-risk-endpoints": ({ topEndpoints }, _mode, t) => (
    <Panel title={t("overview.highestRiskEndpoints")} subtitle={t("overview.currentRiskSnapshot")}>
      {topEndpoints.length ? <div className="link-list">{topEndpoints.map((endpoint) => (
        <Link key={endpoint.endpointId} to={`/endpoints/${endpoint.endpointId}`}>
          <span><strong>{endpoint.hostname}</strong><small>{t("overview.endpointActiveAlerts", { endpointId: endpoint.endpointId, count: endpoint.risk.activeAlertCount })}</small></span>
          <span><strong>{endpoint.risk.score}</strong><StatusPill value={endpoint.risk.level} /></span>
        </Link>
      ))}</div> : <EmptyState title={t("overview.noEndpoints")} message={t("overview.noEndpointRiskSnapshot")} />}
    </Panel>
  ),
  "incident-queue": ({ incidentQueue }, _mode, t) => (
    <Panel title={t("overview.incidentQueueWidget")} subtitle={t("overview.recentOpenIncidents")}>
      {incidentQueue.length ? <div className="link-list">{incidentQueue.map((incident) => (
        <Link key={incident.incidentId} to={`/incidents/${incident.incidentId}`}>
          <span><strong>{incident.title}</strong><small>{t("overview.incidentAlertCount", { time: formatDateTime(incident.lastDetectedAt), count: incident.alertCount })}</small></span>
          <span><StatusPill value={incident.severity} /><StatusPill value={incident.status} /></span>
        </Link>
      ))}</div> : <EmptyState title={t("overview.noOpenIncidents")} message={t("overview.noOpenIncidentsDescription")} />}
    </Panel>
  ),
};

export const OVERVIEW_WIDGET_REGISTRY: readonly OverviewWidgetRegistration[] = OVERVIEW_WIDGET_DEFINITIONS.map(
  (definition) => ({ ...definition, titleKey: requireTitleKey(definition.id), render: requireRenderer(definition.id) }),
);

export const OVERVIEW_WIDGET_BY_ID = new Map(OVERVIEW_WIDGET_REGISTRY.map((registration) => [registration.id, registration]));

function requireRenderer(widgetId: string): OverviewWidgetRegistration["render"] {
  const renderer = RENDERERS[widgetId];
  if (!renderer) throw new Error(`Missing renderer for overview widget: ${widgetId}`);
  return renderer;
}

function requireTitleKey(widgetId: string): TranslationKey {
  const titleKey = TITLE_KEYS[widgetId];
  if (!titleKey) throw new Error(`Missing title translation key for overview widget: ${widgetId}`);
  return titleKey;
}

function scopedPath(path: string, endpointId: number | undefined, parameter = "endpointId"): string {
  if (endpointId === undefined) return path;
  return `${path}${path.includes("?") ? "&" : "?"}${parameter}=${endpointId}`;
}
