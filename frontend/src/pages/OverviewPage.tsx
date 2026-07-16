import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Clock3, RefreshCw } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { Popover } from "../components/primitives";
import { ErrorState, PartialFailureWarning, StaleWarning } from "../components/ui";
import { OverviewDashboard } from "../features/overview/OverviewDashboard";
import { EndpointScopePicker } from "../features/overview/EndpointScopePicker";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime } from "../lib/format";
import { updateParams } from "../lib/url";
import { pollingInterval } from "../query/policy";

type Translate = ReturnType<typeof useI18n>["t"];

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
  const endpointRankingQuery = { page: 1, size: 5, ...(selectedEndpointId ? { endpointIds: [selectedEndpointId] } : {}), sortBy: "riskScore" as const, sortOrder: "desc" as const };
  const endpointRanking = useQuery({ queryKey: ["overview-risk-endpoints", endpointRankingQuery], queryFn: ({ signal }) => api.endpoints(endpointRankingQuery, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const incidentQuery = { ...scopedTimeQuery, status: "OPEN" as const, page: 1, size: 5, sortOrder: "desc" as const };
  const incidentQueue = useQuery({ queryKey: ["overview-incidents", incidentQuery], queryFn: ({ signal }) => api.incidents(incidentQuery, signal), enabled: time.valid, staleTime: 30_000, refetchInterval: pollingInterval(30_000) });
  const allQueries = [dashboard, endpoints, ingest, endpointRanking, incidentQueue];
  const panelQueries = [dashboard, endpoints, endpointRanking, incidentQueue];
  const refreshing = allQueries.some((query) => query.isFetching);
  const lastRefreshedAt = Math.max(...allQueries.map((query) => query.dataUpdatedAt));
  const refreshData = () => Promise.all(allQueries.map((query) => query.refetch()));
  const hasPanelData = panelQueries.some((query) => Boolean(query.data));
  const totalFailure = panelQueries.every((query) => Boolean(query.error && !query.data));
  const initialError = totalFailure ? panelQueries.map((query) => query.error).find(Boolean) ?? null : null;
  const partialFailure = hasPanelData && allQueries.some((query) => query.error && !query.data);
  const staleError = [dashboard, endpoints, ingest].find((query) => query.isRefetchError)?.error ?? null;
  const dashboardData = {
    dashboard: dashboard.data?.data,
    endpoints: endpoints.data?.data,
    topEndpoints: endpointRanking.data?.data.items ?? [],
    incidentQueue: incidentQueue.data?.data.items ?? [],
    selectedEndpointId,
    timeRange: time.query,
  };

  return (
    <div className="page-stack overview-page">
      <h1 className="sr-only">{t("overview.title")}</h1>
      {!time.valid ? <ErrorState error={new Error(t("filter.invalidRange"))} /> : null}
      {time.valid ? <OverviewToolbar
        lastRefreshedAt={lastRefreshedAt}
        onEndpointChange={(endpointId) => setParams(updateParams(params, { endpointId }))}
        onRefresh={refreshData}
        params={params}
        refreshing={refreshing}
        selectedEndpointId={selectedEndpointId}
        setParams={setParams}
        timePreset={time.preset}
      /> : null}
      {partialFailure ? <PartialFailureWarning message={t("overview.partialFailure")} /> : null}
      {staleError && hasPanelData ? <StaleWarning error={staleError} onRetry={() => void refreshData()} /> : null}
      {initialError ? <ErrorState error={initialError} onRetry={() => void refreshData()} /> : null}
      {time.valid && !totalFailure ? <OverviewDashboard data={dashboardData} queueState={{
        endpoints: { pending: endpointRanking.isPending, error: endpointRanking.error, stale: endpointRanking.isRefetchError, onRetry: () => void endpointRanking.refetch() },
        incidents: { pending: incidentQueue.isPending, error: incidentQueue.error, stale: incidentQueue.isRefetchError, onRetry: () => void incidentQueue.refetch() },
      }} summaryState={{
        dashboard: { pending: dashboard.isPending, error: dashboard.error, stale: dashboard.isRefetchError, onRetry: () => void dashboard.refetch() },
        endpoints: { pending: endpoints.isPending, error: endpoints.error, stale: endpoints.isRefetchError, onRetry: () => void endpoints.refetch() },
      }} /> : null}
    </div>
  );
}

function OverviewToolbar({ lastRefreshedAt, onEndpointChange, onRefresh, params, refreshing, selectedEndpointId, setParams, timePreset }: {
  lastRefreshedAt: number;
  onEndpointChange: (endpointId: number | undefined) => void;
  onRefresh: () => Promise<unknown>;
  params: URLSearchParams;
  refreshing: boolean;
  selectedEndpointId: number | undefined;
  setParams: (next: URLSearchParams) => void;
  timePreset: string;
}) {
  const { t } = useI18n();
  return <section className="overview-toolbar" aria-label={t("overview.toolbarAria")}>
    <div className="overview-toolbar-controls">
      <EndpointScopePicker onChange={onEndpointChange} selectedEndpointId={selectedEndpointId} />
      <Popover className="overview-toolbar-popover time" label={t("filter.timeRange")} trigger={<><Clock3 aria-hidden="true" size={15} /><span>{timePresetLabel(timePreset, t)}</span><ChevronDown aria-hidden="true" size={14} /></>}>
        <div className="overview-time-fields"><TimeFilterFields params={params} setParams={setParams} /></div>
      </Popover>
      <button aria-busy={refreshing} className="button ghost overview-refresh" disabled={refreshing} onClick={() => void onRefresh()} type="button"><RefreshCw aria-hidden="true" className={refreshing ? "spin" : ""} size={15} />{refreshing ? t("overview.refreshing") : t("overview.refresh")}</button>
    </div>
    <span className="overview-refresh-meta">{t("overview.lastRefreshed", { time: lastRefreshedAt ? formatDateTime(new Date(lastRefreshedAt).toISOString()) : t("overview.notYet") })}<small>{t("overview.autoRefresh")}</small></span>
  </section>;
}

function timePresetLabel(preset: string, t: Translate): string {
  if (preset === "LATEST_15M") return t("filter.latest15Minutes");
  if (preset === "LATEST_1H") return t("filter.latestHour");
  if (preset === "LATEST_7D") return t("filter.latest7Days");
  if (preset === "CUSTOM") return t("filter.customUtcRange");
  return t("filter.latest24Hours");
}
