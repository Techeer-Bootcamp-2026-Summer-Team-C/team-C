import { Activity, BellRing, Database, HardDrive, Server, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { CountBars, IncidentSeriesChart, SeverityDonut, TimeSeriesChart } from "../components/charts";
import { EdrStatePill, EmptyState, KpiCard, Panel, ResponseGuidance, StatusPill } from "../components/ui";
import type { DashboardSummaryDto, EndpointDto, EndpointSummaryDto, IncidentDto, IngestSummaryDto } from "../contracts";
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
  render: (data: OverviewWidgetData, mode: WidgetDisplayMode) => ReactNode;
}

const RENDERERS: Record<string, OverviewWidgetRegistration["render"]> = {
  "edr-state": ({ dashboard }) => (
    <EdrStatePill calculatedAt={dashboard.edrState.calculatedAt} reasons={dashboard.edrState.reasonCodes}
      score={dashboard.edrState.score} state={dashboard.edrState.status} />
  ),
  "kpi-events": ({ dashboard }) => (
    <KpiCard detail="Events in selected range" icon={<Activity size={18} />} label="Events" to="/events"
      value={dashboard.events.totalCount} />
  ),
  "kpi-alerts": ({ dashboard }) => (
    <KpiCard detail="Alerts in selected range" icon={<BellRing size={18} />} label="Alerts" to="/alerts"
      tone="warning" value={dashboard.alerts.totalCount} />
  ),
  "kpi-open-incidents": ({ dashboard }) => (
    <KpiCard detail="Currently open" icon={<ShieldCheck size={18} />} label="Open incidents"
      to="/incidents?status=OPEN" tone="critical" value={dashboard.incidents.openCount} />
  ),
  "kpi-online-endpoints": ({ dashboard }) => (
    <KpiCard detail="Current snapshot" icon={<Server size={18} />} label="Online endpoints"
      to="/endpoints?status=ONLINE" tone="success" value={dashboard.endpoints.onlineCount} />
  ),
  "kpi-event-failures": ({ dashboard }) => (
    <KpiCard detail="Current failure rows" icon={<Database size={18} />} label="Event failures" to="/operations"
      tone={dashboard.eventFailures.totalCount ? "warning" : "neutral"} value={dashboard.eventFailures.totalCount} />
  ),
  "kpi-storage-buckets": ({ dashboard }) => (
    <KpiCard detail="All lifecycle buckets" icon={<HardDrive size={18} />} label="Storage buckets"
      to="/operations/archives" value={dashboard.storage.totalBucketCount} />
  ),
  "alert-severity": ({ dashboard }, mode) => (
    <Panel title="Alert severity" subtitle="Server-provided distribution">
      <SeverityDonut mode={mode} rows={dashboard.alerts.bySeverity} total={dashboard.alerts.totalCount} />
    </Panel>
  ),
  "event-volume": ({ dashboard }, mode) => (
    <Panel title="Event volume" subtitle="Server-provided time buckets">
      <TimeSeriesChart label="Event" mode={mode} rows={dashboard.events.timeSeries} />
    </Panel>
  ),
  "alert-volume": ({ dashboard }, mode) => (
    <Panel title="Alert volume" subtitle="Server-provided time buckets">
      <TimeSeriesChart label="Alert" mode={mode} rows={dashboard.alerts.timeSeries} />
    </Panel>
  ),
  "incident-activity": ({ dashboard }, mode) => (
    <Panel title="Incident activity" subtitle="Open and closed buckets">
      <IncidentSeriesChart mode={mode} rows={dashboard.incidents.timeSeries} />
    </Panel>
  ),
  "endpoint-risk": ({ endpoints }, mode) => (
    <Panel title="Endpoint risk" subtitle="Current query-time snapshot"
      meta={<span>Highest {endpoints.risk.highestScore ?? "None"}</span>}>
      <CountBars mode={mode} rows={endpoints.risk.byLevel.map((row) => ({
        label: humanize(row.level), count: row.count, tone: row.level.toLowerCase(),
      }))} />
    </Panel>
  ),
  "highest-risk-endpoints": ({ topEndpoints }) => (
    <Panel title="Highest-risk endpoints" subtitle="Current Backend-calculated risk snapshot">
      {topEndpoints.length ? <div className="link-list">{topEndpoints.map((endpoint) => (
        <Link key={endpoint.endpointId} to={`/endpoints/${endpoint.endpointId}`}>
          <span><strong>{endpoint.hostname}</strong><small>Endpoint {endpoint.endpointId} · {endpoint.risk.activeAlertCount} active Alert(s)</small></span>
          <span><strong>{endpoint.risk.score}</strong><StatusPill value={endpoint.risk.level} /></span>
        </Link>
      ))}</div> : <EmptyState title="No Endpoints" message="No Endpoint risk snapshot is available." />}
    </Panel>
  ),
  "incident-queue": ({ incidentQueue }) => (
    <Panel title="Incident queue" subtitle="Five most recent open Incidents">
      {incidentQueue.length ? <div className="link-list">{incidentQueue.map((incident) => (
        <Link key={incident.incidentId} to={`/incidents/${incident.incidentId}`}>
          <span><strong>{incident.title}</strong><small>{formatDateTime(incident.lastDetectedAt)} · {incident.alertCount} Alert(s)</small></span>
          <span><StatusPill value={incident.severity} /><StatusPill value={incident.status} /></span>
        </Link>
      ))}</div> : <EmptyState title="No open Incidents" message="The selected time range has no open Incident rows." />}
    </Panel>
  ),
  "response-guidance": ({ dashboard }) => (
    <Panel title="Response guidance summary"
      subtitle={`${dashboard.responseGuidance.affectedAlertCount} active Alerts across ${dashboard.responseGuidance.ruleCount} Rule versions`}
      meta={<span>{dashboard.responseGuidance.manualActionStepCount} manual steps</span>}>
      <ResponseGuidance steps={dashboard.responseGuidance.steps} />
    </Panel>
  ),
  "endpoint-operating-systems": ({ endpoints }, mode) => (
    <Panel title="Endpoint operating systems" subtitle="Current Endpoint snapshot">
      <CountBars mode={mode} rows={endpoints.byOsType.map((row) => ({ label: row.osType, count: row.count }))} />
    </Panel>
  ),
  "sensor-health": ({ endpoints }, mode) => (
    <Panel title="Sensor health" subtitle="Current reported sensor snapshots">
      <CountBars mode={mode} rows={endpoints.sensorHealth.map((row) => ({
        label: `${row.sensor} · ${humanize(row.status)}`, count: row.count, tone: row.status.toLowerCase(),
      }))} />
    </Panel>
  ),
  "top-rules": ({ dashboard }, mode) => (
    <Panel title="Top rules" subtitle="Alerts in selected range">
      <CountBars mode={mode} rows={dashboard.alerts.topRules.map((row) => ({
        label: `${row.ruleName} · ${row.ruleCode}`, count: row.count,
      }))} />
    </Panel>
  ),
  "mitre-distribution": ({ dashboard }, mode) => (
    <Panel title="MITRE detection distribution" subtitle="Tactics and techniques observed in Alert snapshots">
      <CountBars mode={mode} rows={[
        ...dashboard.alerts.mitreTactics.map((row) => ({ label: `${row.mitreTacticCode} · ${row.mitreTacticName}`, count: row.count })),
        ...dashboard.alerts.mitreTechniques.map((row) => ({ label: `${row.mitreTechniqueCode} · ${row.mitreTechniqueName}`, count: row.count })),
      ]} />
    </Panel>
  ),
  "process-network-signals": ({ dashboard }, mode) => (
    <Panel title="Process and network signals" subtitle="Top values returned by the Backend">
      <CountBars mode={mode} rows={[
        ...dashboard.events.topProcesses.map((row) => ({ label: `Process · ${row.processName}`, count: row.count })),
        ...dashboard.events.topRemoteIps.map((row) => ({ label: `IP · ${row.remoteIp}`, count: row.count })),
        ...dashboard.events.topDomains.map((row) => ({ label: `Domain · ${row.domain}`, count: row.count })),
      ]} />
    </Panel>
  ),
  "file-dns-l7-signals": ({ dashboard }, mode) => (
    <Panel title="File, DNS, and L7 signals" subtitle="Top values returned by the Backend">
      <CountBars mode={mode} rows={[
        ...dashboard.events.topFileHashes.map((row) => ({ label: `Hash · ${row.fileHashSha256}`, count: row.count })),
        ...dashboard.events.topDnsQueries.map((row) => ({ label: `DNS · ${row.dnsQuery}`, count: row.count })),
        ...dashboard.events.topL7Protocols.map((row) => ({ label: `L7 · ${row.l7Protocol}`, count: row.count })),
      ]} />
    </Panel>
  ),
  "failure-distribution": ({ dashboard, ingest }, mode) => (
    <Panel title="Failure distribution" subtitle={`Oldest failed ${formatDateTime(ingest.eventFailures.oldestFailedAt)}`}>
      <CountBars mode={mode} rows={[
        ...dashboard.eventFailures.byStage.map((row) => ({ label: `Stage · ${humanize(row.failureStage)}`, count: row.count })),
        ...dashboard.eventFailures.byCode.map((row) => ({ label: `Code · ${row.failureCode ?? "None"}`, count: row.count })),
        ...dashboard.eventFailures.byStatus.map((row) => ({ label: `Status · ${humanize(row.status)}`, count: row.count })),
      ]} />
    </Panel>
  ),
  "storage-distribution": ({ dashboard }, mode) => (
    <Panel title="Storage distribution" subtitle="Current lifecycle snapshot">
      <CountBars mode={mode} rows={[
        ...dashboard.storage.byBackend.map((row) => ({ label: `Backend · ${row.storageBackend}`, count: row.count })),
        ...dashboard.storage.byClass.map((row) => ({ label: `Class · ${humanize(row.storageClass)}`, count: row.count })),
        ...dashboard.storage.byStatus.map((row) => ({ label: `Status · ${humanize(row.storageStatus)}`, count: row.count })),
      ]} />
    </Panel>
  ),
};

export const OVERVIEW_WIDGET_REGISTRY: readonly OverviewWidgetRegistration[] = OVERVIEW_WIDGET_DEFINITIONS.map(
  (definition) => ({ ...definition, render: requireRenderer(definition.id) }),
);

export const OVERVIEW_WIDGET_BY_ID = new Map(OVERVIEW_WIDGET_REGISTRY.map((registration) => [registration.id, registration]));

function requireRenderer(widgetId: string): OverviewWidgetRegistration["render"] {
  const renderer = RENDERERS[widgetId];
  if (!renderer) throw new Error(`Missing renderer for overview widget: ${widgetId}`);
  return renderer;
}
