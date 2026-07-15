import { Activity, BellRing, Database, HardDrive, Server, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { CountBars, IncidentSeriesChart, SeverityDonut, TimeSeriesChart } from "../components/charts";
import { EdrStatePill, EmptyState, KpiCard, Panel, ResponseGuidance, StatusPill } from "../components/ui";
import type { DashboardSummaryDto, EndpointDto, EndpointSummaryDto, IncidentDto, IngestSummaryDto } from "../contracts";
import type { TranslationKey } from "../i18n/translations";
import type { TranslationParams } from "../i18n/types";
import { formatDateTime, humanize } from "../lib/format";
import {
  OVERVIEW_WIDGET_DEFINITIONS,
  type OverviewWidgetDefinition,
  type WidgetDisplayMode,
} from "./dashboardLayout";

export interface OverviewWidgetData {
  dashboard: DashboardSummaryDto;
  endpoints: EndpointSummaryDto;
  ingest: IngestSummaryDto;
  topEndpoints: EndpointDto[];
  incidentQueue: IncidentDto[];
}

export interface OverviewWidgetRegistration extends OverviewWidgetDefinition {
  titleKey: TranslationKey;
  render: (data: OverviewWidgetData, mode: WidgetDisplayMode, t: Translate) => ReactNode;
}

type Translate = (key: TranslationKey, params?: TranslationParams) => string;

const TITLE_KEYS: Record<string, TranslationKey> = {
  "edr-state": "edrState.current",
  "kpi-events": "overview.events",
  "kpi-alerts": "overview.alerts",
  "kpi-open-incidents": "overview.openIncidents",
  "kpi-online-endpoints": "overview.onlineEndpoints",
  "kpi-event-failures": "overview.eventFailures",
  "kpi-storage-buckets": "overview.storageBuckets",
  "alert-severity": "overview.alertSeverity",
  "event-volume": "overview.eventVolume",
  "alert-volume": "overview.alertVolume",
  "incident-activity": "overview.incidentActivity",
  "endpoint-risk": "overview.endpointRisk",
  "highest-risk-endpoints": "overview.highestRiskEndpoints",
  "incident-queue": "overview.incidentQueueWidget",
  "response-guidance": "overview.responseGuidanceSummary",
  "endpoint-operating-systems": "overview.endpointOs",
  "sensor-health": "overview.sensorHealth",
  "top-rules": "overview.topRules",
  "mitre-distribution": "overview.mitreDistribution",
  "process-network-signals": "overview.processNetwork",
  "file-dns-l7-signals": "overview.fileDnsL7",
  "failure-distribution": "overview.failureDistribution",
  "storage-distribution": "overview.storageDistribution",
};

const RENDERERS: Record<string, OverviewWidgetRegistration["render"]> = {
  "edr-state": ({ dashboard }) => (
    <EdrStatePill calculatedAt={dashboard.edrState.calculatedAt} reasons={dashboard.edrState.reasonCodes}
      score={dashboard.edrState.score} state={dashboard.edrState.status} />
  ),
  "kpi-events": ({ dashboard }, _mode, t) => (
    <KpiCard detail={t("overview.eventsDetail")} icon={<Activity size={18} />} label={t("overview.events")} to="/events"
      value={dashboard.events.totalCount} />
  ),
  "kpi-alerts": ({ dashboard }, _mode, t) => (
    <KpiCard detail={t("overview.alertsDetail")} icon={<BellRing size={18} />} label={t("overview.alerts")} to="/alerts"
      tone="warning" value={dashboard.alerts.totalCount} />
  ),
  "kpi-open-incidents": ({ dashboard }, _mode, t) => (
    <KpiCard detail={t("overview.currentlyOpen")} icon={<ShieldCheck size={18} />} label={t("overview.openIncidents")}
      to="/incidents?status=OPEN" tone="critical" value={dashboard.incidents.openCount} />
  ),
  "kpi-online-endpoints": ({ dashboard }, _mode, t) => (
    <KpiCard detail={t("overview.currentSnapshot")} icon={<Server size={18} />} label={t("overview.onlineEndpoints")}
      to="/endpoints?status=ONLINE" tone="success" value={dashboard.endpoints.onlineCount} />
  ),
  "kpi-event-failures": ({ dashboard }, _mode, t) => (
    <KpiCard detail={t("overview.currentFailureRows")} icon={<Database size={18} />} label={t("overview.eventFailures")} to="/operations"
      tone={dashboard.eventFailures.totalCount ? "warning" : "neutral"} value={dashboard.eventFailures.totalCount} />
  ),
  "kpi-storage-buckets": ({ dashboard }, _mode, t) => (
    <KpiCard detail={t("overview.allLifecycleBuckets")} icon={<HardDrive size={18} />} label={t("overview.storageBuckets")}
      to="/operations/archives" value={dashboard.storage.totalBucketCount} />
  ),
  "alert-severity": ({ dashboard }, mode, t) => (
    <Panel title={t("overview.alertSeverity")} subtitle={t("overview.serverDistribution")}>
      <SeverityDonut mode={mode} rows={dashboard.alerts.bySeverity} total={dashboard.alerts.totalCount} />
    </Panel>
  ),
  "event-volume": ({ dashboard }, mode, t) => (
    <Panel title={t("overview.eventVolume")} subtitle={t("overview.serverBuckets")}>
      <TimeSeriesChart label="Event" mode={mode} rows={dashboard.events.timeSeries} />
    </Panel>
  ),
  "alert-volume": ({ dashboard }, mode, t) => (
    <Panel title={t("overview.alertVolume")} subtitle={t("overview.serverBuckets")}>
      <TimeSeriesChart label="Alert" mode={mode} rows={dashboard.alerts.timeSeries} />
    </Panel>
  ),
  "incident-activity": ({ dashboard }, mode, t) => (
    <Panel title={t("overview.incidentActivity")} subtitle={t("overview.openClosedBuckets")}>
      <IncidentSeriesChart mode={mode} rows={dashboard.incidents.timeSeries} />
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
  "response-guidance": ({ dashboard }, _mode, t) => (
    <Panel title={t("overview.responseGuidanceSummary")}
      subtitle={t("overview.responseGuidanceCount", { alerts: dashboard.responseGuidance.affectedAlertCount, rules: dashboard.responseGuidance.ruleCount })}
      meta={<span>{t("overview.manualSteps", { count: dashboard.responseGuidance.manualActionStepCount })}</span>}>
      <ResponseGuidance steps={dashboard.responseGuidance.steps} />
    </Panel>
  ),
  "endpoint-operating-systems": ({ endpoints }, mode, t) => (
    <Panel title={t("overview.endpointOs")} subtitle={t("overview.endpointSnapshot")}>
      <CountBars mode={mode} rows={endpoints.byOsType.map((row) => ({ label: row.osType, count: row.count }))} />
    </Panel>
  ),
  "sensor-health": ({ endpoints }, mode, t) => (
    <Panel title={t("overview.sensorHealth")} subtitle={t("overview.sensorSnapshots")}>
      <CountBars mode={mode} rows={endpoints.sensorHealth.map((row) => ({
        label: `${row.sensor} · ${humanize(row.status)}`, count: row.count, tone: row.status.toLowerCase(),
      }))} />
    </Panel>
  ),
  "top-rules": ({ dashboard }, mode, t) => (
    <Panel title={t("overview.topRules")} subtitle={t("overview.alertsDetail")}>
      <CountBars mode={mode} rows={dashboard.alerts.topRules.map((row) => ({
        label: `${row.ruleName} · ${row.ruleCode}`, count: row.count,
      }))} />
    </Panel>
  ),
  "mitre-distribution": ({ dashboard }, mode, t) => (
    <Panel title={t("overview.mitreDistribution")} subtitle={t("overview.mitreSubtitle")}>
      <CountBars mode={mode} rows={[
        ...dashboard.alerts.mitreTactics.map((row) => ({ label: `${row.mitreTacticCode} · ${row.mitreTacticName}`, count: row.count })),
        ...dashboard.alerts.mitreTechniques.map((row) => ({ label: `${row.mitreTechniqueCode} · ${row.mitreTechniqueName}`, count: row.count })),
      ]} />
    </Panel>
  ),
  "process-network-signals": ({ dashboard }, mode, t) => (
    <Panel title={t("overview.processNetwork")} subtitle={t("overview.backendTopValues")}>
      <CountBars mode={mode} rows={[
        ...dashboard.events.topProcesses.map((row) => ({ label: `Process · ${row.processName}`, count: row.count })),
        ...dashboard.events.topRemoteIps.map((row) => ({ label: `IP · ${row.remoteIp}`, count: row.count })),
        ...dashboard.events.topDomains.map((row) => ({ label: `Domain · ${row.domain}`, count: row.count })),
      ]} />
    </Panel>
  ),
  "file-dns-l7-signals": ({ dashboard }, mode, t) => (
    <Panel title={t("overview.fileDnsL7")} subtitle={t("overview.backendTopValues")}>
      <CountBars mode={mode} rows={[
        ...dashboard.events.topFileHashes.map((row) => ({ label: `Hash · ${row.fileHashSha256}`, count: row.count })),
        ...dashboard.events.topDnsQueries.map((row) => ({ label: `DNS · ${row.dnsQuery}`, count: row.count })),
        ...dashboard.events.topL7Protocols.map((row) => ({ label: `L7 · ${row.l7Protocol}`, count: row.count })),
      ]} />
    </Panel>
  ),
  "failure-distribution": ({ dashboard, ingest }, mode, t) => (
    <Panel title={t("overview.failureDistribution")} subtitle={t("overview.oldestFailed", { time: formatDateTime(ingest.eventFailures.oldestFailedAt) })}>
      <CountBars mode={mode} rows={[
        ...dashboard.eventFailures.byStage.map((row) => ({ label: `${t("operations.stage")} · ${humanize(row.failureStage)}`, count: row.count })),
        ...dashboard.eventFailures.byCode.map((row) => ({ label: `Code · ${row.failureCode ?? t("common.none")}`, count: row.count })),
        ...dashboard.eventFailures.byStatus.map((row) => ({ label: `${t("filter.status")} · ${humanize(row.status)}`, count: row.count })),
      ]} />
    </Panel>
  ),
  "storage-distribution": ({ dashboard }, mode, t) => (
    <Panel title={t("overview.storageDistribution")} subtitle={t("overview.lifecycleSnapshot")}>
      <CountBars mode={mode} rows={[
        ...dashboard.storage.byBackend.map((row) => ({ label: `Backend · ${row.storageBackend}`, count: row.count })),
        ...dashboard.storage.byClass.map((row) => ({ label: `Class · ${humanize(row.storageClass)}`, count: row.count })),
        ...dashboard.storage.byStatus.map((row) => ({ label: `Status · ${humanize(row.storageStatus)}`, count: row.count })),
      ]} />
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
