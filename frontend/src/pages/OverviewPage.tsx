import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Settings2 } from "lucide-react";
import { memo, useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { Button } from "../components/primitives";
import { ErrorState, PageHeader, PartialFailureWarning, StaleWarning } from "../components/ui";
import { useAuth } from "../auth/AuthContext";
import { OverviewLayoutProvider } from "../features/overviewLayout/OverviewLayoutContext";
import { OverviewDashboardWorkspace } from "../features/overviewLayout/OverviewDashboardWorkspace";
import { EndpointScopePicker } from "../features/overview/EndpointScopePicker";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime } from "../lib/format";
import { updateParams } from "../lib/url";

export function readOverviewEndpointId(params: URLSearchParams): number | undefined {
  const endpointId = Number(params.get("endpointId"));
  return Number.isInteger(endpointId) && endpointId > 0 ? endpointId : undefined;
}

export function OverviewPage() {
  return <AuthenticatedOverviewRoute mode="overview" />;
}

export function DashboardManagementPage() {
  return <AuthenticatedOverviewRoute mode="manage" />;
}

function AuthenticatedOverviewRoute({ mode }: { mode: "overview" | "manage" }) {
  const auth = useAuth();
  if (!auth.user) return null;
  return <OverviewLayoutProvider key={`${auth.user.userId}-${mode}`} userId={auth.user.userId}><OverviewPageContent mode={mode} /></OverviewLayoutProvider>;
}

function OverviewPageContent({ mode }: { mode: "overview" | "manage" }) {
  const { t } = useI18n();
  const [dashboardSettingsOpen, setDashboardSettingsOpen] = useState(false);
  const [manualRefreshing, setManualRefreshing] = useState(false);
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const selectedEndpointId = readOverviewEndpointId(params);
  const scopedTimeQuery = {
    ...time.query,
    ...(selectedEndpointId ? { endpointId: selectedEndpointId } : {}),
  };
  const summaryQuery = { ...scopedTimeQuery, interval: time.interval };
  const dashboard = useQuery({ queryKey: ["dashboard", summaryQuery], queryFn: ({ signal }) => api.dashboard(summaryQuery, signal), enabled: time.valid, staleTime: 30_000 });
  const endpoints = useQuery({ queryKey: ["endpoint-summary", scopedTimeQuery], queryFn: ({ signal }) => api.endpointSummary(scopedTimeQuery, signal), enabled: time.valid, staleTime: 30_000 });
  const ingest = useQuery({ queryKey: ["ingest-summary", scopedTimeQuery], queryFn: ({ signal }) => api.ingestSummary(scopedTimeQuery, signal), enabled: time.valid, staleTime: 30_000 });
  const endpointRankingQuery = { page: 1, size: 5, ...(selectedEndpointId ? { endpointIds: [selectedEndpointId] } : {}), sortBy: "riskScore" as const, sortOrder: "desc" as const };
  const endpointRanking = useQuery({ queryKey: ["overview-risk-endpoints", endpointRankingQuery], queryFn: ({ signal }) => api.endpoints(endpointRankingQuery, signal), enabled: time.valid, staleTime: 30_000 });
  const incidentQuery = { ...scopedTimeQuery, status: "OPEN" as const, page: 1, size: 5, sortOrder: "desc" as const };
  const incidentQueue = useQuery({ queryKey: ["overview-incidents", incidentQuery], queryFn: ({ signal }) => api.incidents(incidentQuery, signal), enabled: time.valid, staleTime: 30_000 });
  const allQueries = [dashboard, endpoints, ingest, endpointRanking, incidentQueue];
  const panelQueries = [dashboard, endpoints, endpointRanking, incidentQueue];
  const lastRefreshedAt = Math.max(...allQueries.map((query) => query.dataUpdatedAt));
  const refreshData = () => Promise.all(allQueries.map((query) => query.refetch()));
  const refreshManually = async () => {
    if (manualRefreshing) return;
    setManualRefreshing(true);
    try {
      await refreshData();
    } finally {
      setManualRefreshing(false);
    }
  };
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
    <div className={`page-stack overview-page${mode === "manage" ? " dashboard-workbench-page" : ""}`}>
      {mode === "manage" ? <PageHeader
        actions={<>
          <Link className="button ghost" to={{ pathname: "/", search: params.toString() ? `?${params.toString()}` : "" }}>{t("dashboard.openOverview")}</Link>
          <Button onClick={() => setDashboardSettingsOpen(true)} type="button" variant="ghost"><Settings2 aria-hidden="true" size={16} />{t("dashboard.settings")}</Button>
        </>}
        description={t("dashboard.workbenchDescription")}
        eyebrow={t("dashboard.workbenchEyebrow")}
        title={t("dashboard.workbenchTitle")}
      /> : <h1 className="sr-only">{t("overview.title")}</h1>}
      {!time.valid ? <ErrorState error={new Error(t("filter.invalidRange"))} /> : null}
      {time.valid ? <OverviewToolbar
        dashboardSettingsTo={mode === "overview" ? `/dashboards${params.toString() ? `?${params.toString()}` : ""}` : undefined}
        lastRefreshedAt={lastRefreshedAt}
        onRefresh={refreshManually}
        params={params}
        refreshing={manualRefreshing}
        selectedEndpointId={selectedEndpointId}
        setParams={setParams}
      /> : null}
      {partialFailure ? <PartialFailureWarning message={t("overview.partialFailure")} /> : null}
      {staleError && hasPanelData ? <StaleWarning error={staleError} onRetry={() => void refreshData()} /> : null}
      {initialError ? <ErrorState error={initialError} onRetry={() => void refreshData()} /> : null}
      {time.valid && !totalFailure ? <OverviewDashboardWorkspace data={dashboardData} mode={mode} onSettingsClose={() => setDashboardSettingsOpen(false)} queueState={{
        endpoints: { pending: endpointRanking.isPending, error: endpointRanking.error, stale: endpointRanking.isRefetchError, onRetry: () => void endpointRanking.refetch() },
        incidents: { pending: incidentQueue.isPending, error: incidentQueue.error, stale: incidentQueue.isRefetchError, onRetry: () => void incidentQueue.refetch() },
      }} settingsOpen={dashboardSettingsOpen} summaryState={{
        dashboard: { pending: dashboard.isPending, error: dashboard.error, stale: dashboard.isRefetchError, onRetry: () => void dashboard.refetch() },
        endpoints: { pending: endpoints.isPending, error: endpoints.error, stale: endpoints.isRefetchError, onRetry: () => void endpoints.refetch() },
      }} /> : null}
    </div>
  );
}

function OverviewToolbar({ dashboardSettingsTo, lastRefreshedAt, onRefresh, params, refreshing, selectedEndpointId, setParams }: {
  dashboardSettingsTo?: string | undefined;
  lastRefreshedAt: number;
  onRefresh: () => Promise<unknown>;
  params: URLSearchParams;
  refreshing: boolean;
  selectedEndpointId: number | undefined;
  setParams: (next: URLSearchParams) => void;
}) {
  const { t } = useI18n();
  return <section className="overview-toolbar" aria-label={t("overview.toolbarAria")}>
    <div className="overview-toolbar-controls">
      <OverviewScopeControls params={params} selectedEndpointId={selectedEndpointId} setParams={setParams} />
      <button aria-busy={refreshing} className="button ghost overview-refresh" disabled={refreshing} onClick={() => void onRefresh()} type="button"><RefreshCw aria-hidden="true" className={refreshing ? "spin" : ""} size={15} />{refreshing ? t("overview.refreshing") : t("overview.refresh")}</button>
      {dashboardSettingsTo ? <Link className="button ghost overview-refresh" to={dashboardSettingsTo}><Settings2 aria-hidden="true" size={15} />{t("dashboard.settings")}</Link> : null}
    </div>
    <span className="overview-refresh-meta">{t("overview.lastRefreshed", { time: lastRefreshedAt ? formatDateTime(new Date(lastRefreshedAt).toISOString()) : t("overview.notYet") })}</span>
  </section>;
}

const OverviewScopeControls = memo(function OverviewScopeControls({ params, selectedEndpointId, setParams }: {
  params: URLSearchParams;
  selectedEndpointId: number | undefined;
  setParams: (next: URLSearchParams) => void;
}) {
  const onEndpointChange = useCallback((endpointId: number | undefined) => {
    setParams(updateParams(params, { endpointId }));
  }, [params, setParams]);

  return <>
    <EndpointScopePicker onChange={onEndpointChange} selectedEndpointId={selectedEndpointId} />
    <div className="overview-time-select"><TimeFilterFields params={params} setParams={setParams} /></div>
  </>;
});
