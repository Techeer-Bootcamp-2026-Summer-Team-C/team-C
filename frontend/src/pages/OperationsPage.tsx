import { useQuery } from "@tanstack/react-query";
import { Archive, Database, HardDrive, RefreshCcw } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { ErrorState, GlobalFilterBar, KpiCard, PageHeader, Panel, Skeleton, StaleWarning } from "../components/ui";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime } from "../lib/format";
import { pollingInterval } from "../query/policy";

export function OperationsPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const result = useQuery({ queryKey: ["ingest-summary", time.query], queryFn: ({ signal }) => api.ingestSummary(time.query, signal), enabled: time.valid, staleTime: 15_000, refetchInterval: pollingInterval(15_000) });
  return <div className="page-stack">
    <PageHeader eyebrow={t("operations.eyebrow")} title={t("operations.title")} description={t("operations.description")} actions={<Link className="button" to="/operations/archives"><Archive aria-hidden="true" size={16} />{t("operations.archiveAction")}</Link>} />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}><TimeFilterFields params={params} setParams={setParams} /></GlobalFilterBar>
    {result.isPending ? <Skeleton rows={8} /> : null}
    {result.error && !result.data ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.isRefetchError && result.data ? <StaleWarning error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <OperationsContent data={result.data.data} /> : null}
  </div>;
}

function OperationsContent({ data }: { data: import("../contracts").IngestSummaryDto }) {
  const { t } = useI18n();
  return <>
    <section className="kpi-grid operations-kpis">
      <KpiCard detail={t("common.latest", { time: formatDateTime(data.events.latestIngestedAt) })} icon={<Database size={18} />} label={t("operations.ingestedEvents")} value={data.events.ingestedCount} />
      <KpiCard detail={t("common.oldest", { time: formatDateTime(data.eventFailures.oldestFailedAt) })} icon={<RefreshCcw size={18} />} label={t("operations.failed")} tone={data.eventFailures.failedCount ? "critical" : "neutral"} value={data.eventFailures.failedCount} />
      <KpiCard detail={t("operations.reprocessedDetail")} icon={<RefreshCcw size={18} />} label={t("operations.reprocessed")} value={data.eventFailures.reprocessedCount} />
      <KpiCard detail={t("operations.reprocessFailedDetail")} icon={<RefreshCcw size={18} />} label={t("operations.reprocessFailed")} tone={data.eventFailures.reprocessFailedCount ? "warning" : "neutral"} value={data.eventFailures.reprocessFailedCount} />
    </section>
    <Panel title={t("operations.storageLifecycle")} subtitle={t("operations.storageSubtitle")}><section className="storage-grid">
      <StorageCount label="ClickHouse HOT" value={data.storage.clickhouseHotBucketCount} />
      <StorageCount label="RESTORED" value={data.storage.restoredBucketCount} />
      <StorageCount label="ARCHIVED" value={data.storage.glacierArchivedBucketCount} />
      <StorageCount label="RESTORE REQUESTED" value={data.storage.restoringBucketCount} />
      <StorageCount label="RESTORE FAILED" value={data.storage.failedBucketCount} />
      <StorageCount label="EXPIRED" value={data.storage.expiredBucketCount} />
    </section></Panel>
    <Panel title={t("operations.boundary")} subtitle={t("operations.boundarySubtitle")}><div className="boundary-note"><HardDrive aria-hidden="true" size={22} /><div><strong>{t("operations.noWebReplay")}</strong><p>{t("operations.boundaryDescription")}</p></div></div></Panel>
  </>;
}

function StorageCount({ label, value }: { label: string; value: number }) {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}
