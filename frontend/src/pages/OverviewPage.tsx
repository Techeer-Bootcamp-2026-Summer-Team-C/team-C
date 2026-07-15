import { Activity, BellRing, Database, HardDrive, Server, ShieldCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { CountBars, IncidentSeriesChart, SeverityDonut, TimeSeriesChart } from "../components/charts";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { EdrStatePill, ErrorState, GlobalFilterBar, KpiCard, PageHeader, Panel, Skeleton, StaleWarning } from "../components/ui";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime, humanize } from "../lib/format";
import { pollingInterval } from "../query/policy";

export function OverviewPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const summaryQuery = { ...time.query, interval: time.interval };
  const dashboard = useQuery({ queryKey: ["dashboard", summaryQuery], queryFn: ({ signal }) => api.dashboard(summaryQuery, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const endpoints = useQuery({ queryKey: ["endpoint-summary", time.query], queryFn: ({ signal }) => api.endpointSummary(time.query, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const ingest = useQuery({ queryKey: ["ingest-summary", time.query], queryFn: ({ signal }) => api.ingestSummary(time.query, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const initialError = dashboard.error ?? endpoints.error ?? ingest.error;
  const loading = dashboard.isPending || endpoints.isPending || ingest.isPending;
  const lastRefreshedAt = Math.max(dashboard.dataUpdatedAt, endpoints.dataUpdatedAt, ingest.dataUpdatedAt);

  return (
    <div className="page-stack">
      <PageHeader eyebrow={t("overview.eyebrow")} title={t("overview.title")} description={t("overview.description")} actions={<span className="last-refreshed">{t("overview.lastRefreshed", { time: lastRefreshedAt ? formatDateTime(new Date(lastRefreshedAt).toISOString()) : t("overview.notYet") })}</span>} />
      <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}><TimeFilterFields params={params} setParams={setParams} /></GlobalFilterBar>
      {!time.valid ? <ErrorState error={new Error("A valid custom time range is required.")} /> : null}
      {loading && time.valid ? <OverviewSkeleton /> : null}
      {initialError && !dashboard.data && !endpoints.data && !ingest.data ? <ErrorState error={initialError} onRetry={() => void Promise.all([dashboard.refetch(), endpoints.refetch(), ingest.refetch()])} /> : null}
      {(dashboard.isRefetchError || endpoints.isRefetchError || ingest.isRefetchError) && dashboard.data && endpoints.data && ingest.data ? <StaleWarning error={initialError} onRetry={() => void Promise.all([dashboard.refetch(), endpoints.refetch(), ingest.refetch()])} /> : null}
      {dashboard.data && endpoints.data && ingest.data ? <OverviewContent dashboard={dashboard.data.data} endpoints={endpoints.data.data} ingest={ingest.data.data} /> : null}
    </div>
  );
}

function OverviewContent({ dashboard, endpoints, ingest }: {
  dashboard: import("../contracts").DashboardSummaryDto;
  endpoints: import("../contracts").EndpointSummaryDto;
  ingest: import("../contracts").IngestSummaryDto;
}) {
  const { t } = useI18n();
  return (
    <>
      <EdrStatePill calculatedAt={dashboard.edrState.calculatedAt} reasons={dashboard.edrState.reasonCodes} score={dashboard.edrState.score} state={dashboard.edrState.status} />
      <section className="kpi-grid" aria-label={t("overview.kpiAria")}>
        <KpiCard detail={t("overview.eventsDetail")} icon={<Activity size={18} />} label={t("overview.events")} to="/events" value={dashboard.events.totalCount} />
        <KpiCard detail={t("overview.alertsDetail")} icon={<BellRing size={18} />} label={t("overview.alerts")} to="/alerts" tone="warning" value={dashboard.alerts.totalCount} />
        <KpiCard detail={t("overview.currentlyOpen")} icon={<ShieldCheck size={18} />} label={t("overview.openIncidents")} to="/incidents?status=OPEN" tone="critical" value={dashboard.incidents.openCount} />
        <KpiCard detail={t("overview.currentSnapshot")} icon={<Server size={18} />} label={t("overview.onlineEndpoints")} to="/endpoints?status=ONLINE" tone="success" value={dashboard.endpoints.onlineCount} />
        <KpiCard detail={t("overview.currentFailureRows")} icon={<Database size={18} />} label={t("overview.eventFailures")} to="/operations" tone={dashboard.eventFailures.totalCount ? "warning" : "neutral"} value={dashboard.eventFailures.totalCount} />
        <KpiCard detail={t("overview.allLifecycleBuckets")} icon={<HardDrive size={18} />} label={t("overview.storageBuckets")} to="/operations/archives" value={dashboard.storage.totalBucketCount} />
      </section>
      <section className="overview-grid">
        <Panel className="span-1" title={t("overview.alertSeverity")} subtitle={t("overview.serverDistribution")}><SeverityDonut rows={dashboard.alerts.bySeverity} total={dashboard.alerts.totalCount} /></Panel>
        <Panel className="span-2" title={t("overview.eventVolume")} subtitle={t("overview.serverBuckets")}><TimeSeriesChart label="Event" rows={dashboard.events.timeSeries} /></Panel>
        <Panel title={t("overview.alertVolume")} subtitle={t("overview.serverBuckets")}><TimeSeriesChart label="Alert" rows={dashboard.alerts.timeSeries} /></Panel>
        <Panel title={t("overview.incidentActivity")} subtitle={t("overview.openClosedBuckets")}><IncidentSeriesChart rows={dashboard.incidents.timeSeries} /></Panel>
        <Panel title={t("overview.endpointRisk")} subtitle={t("overview.querySnapshot")} meta={<span>{t("overview.highest", { value: endpoints.risk.highestScore ?? t("common.none") })}</span>}><CountBars rows={endpoints.risk.byLevel.map((row) => ({ label: humanize(row.level), count: row.count, tone: row.level.toLowerCase() }))} /></Panel>
        <Panel title={t("overview.endpointOs")} subtitle={t("overview.endpointSnapshot")}><CountBars rows={endpoints.byOsType.map((row) => ({ label: row.osType, count: row.count }))} /></Panel>
        <Panel title={t("overview.sensorHealth")} subtitle={t("overview.sensorSnapshots")}><CountBars rows={endpoints.sensorHealth.map((row) => ({ label: `${row.sensor} · ${humanize(row.status)}`, count: row.count, tone: row.status.toLowerCase() }))} /></Panel>
        <Panel title={t("overview.topRules")} subtitle={t("overview.alertsDetail")}><CountBars rows={dashboard.alerts.topRules.map((row) => ({ label: `${row.ruleName} · ${row.ruleCode}`, count: row.count }))} /></Panel>
        <Panel title={t("overview.mitreDistribution")} subtitle={t("overview.mitreSubtitle")}><CountBars rows={[...dashboard.alerts.mitreTactics.map((row) => ({ label: `${row.mitreTacticCode} · ${row.mitreTacticName}`, count: row.count })), ...dashboard.alerts.mitreTechniques.map((row) => ({ label: `${row.mitreTechniqueCode} · ${row.mitreTechniqueName}`, count: row.count }))]} /></Panel>
        <Panel title={t("overview.processNetwork")} subtitle={t("overview.backendTopValues")}><CountBars rows={[...dashboard.events.topProcesses.map((row) => ({ label: `Process · ${row.processName}`, count: row.count })), ...dashboard.events.topRemoteIps.map((row) => ({ label: `IP · ${row.remoteIp}`, count: row.count })), ...dashboard.events.topDomains.map((row) => ({ label: `Domain · ${row.domain}`, count: row.count }))]} /></Panel>
        <Panel title={t("overview.fileDnsL7")} subtitle={t("overview.backendTopValues")}><CountBars rows={[...dashboard.events.topFileHashes.map((row) => ({ label: `Hash · ${row.fileHashSha256}`, count: row.count })), ...dashboard.events.topDnsQueries.map((row) => ({ label: `DNS · ${row.dnsQuery}`, count: row.count })), ...dashboard.events.topL7Protocols.map((row) => ({ label: `L7 · ${row.l7Protocol}`, count: row.count }))]} /></Panel>
        <Panel title={t("overview.failureDistribution")} subtitle={t("overview.oldestFailed", { time: formatDateTime(ingest.eventFailures.oldestFailedAt) })}><CountBars rows={[...dashboard.eventFailures.byStage.map((row) => ({ label: `Stage · ${humanize(row.failureStage)}`, count: row.count })), ...dashboard.eventFailures.byCode.map((row) => ({ label: `Code · ${row.failureCode ?? t("common.none")}`, count: row.count })), ...dashboard.eventFailures.byStatus.map((row) => ({ label: `Status · ${humanize(row.status)}`, count: row.count }))]} /></Panel>
        <Panel title={t("overview.storageDistribution")} subtitle={t("overview.lifecycleSnapshot")}><CountBars rows={[...dashboard.storage.byBackend.map((row) => ({ label: `Backend · ${row.storageBackend}`, count: row.count })), ...dashboard.storage.byClass.map((row) => ({ label: `Class · ${humanize(row.storageClass)}`, count: row.count })), ...dashboard.storage.byStatus.map((row) => ({ label: `Status · ${humanize(row.storageStatus)}`, count: row.count }))]} /></Panel>
      </section>
    </>
  );
}

function OverviewSkeleton() {
  return <><Skeleton rows={2} /><section className="kpi-grid">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} rows={2} />)}</section><section className="overview-grid"><Skeleton rows={5} /><Skeleton rows={5} /><Skeleton rows={5} /></section></>;
}
