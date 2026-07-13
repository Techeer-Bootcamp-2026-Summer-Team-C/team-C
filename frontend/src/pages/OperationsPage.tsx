import { useQuery } from "@tanstack/react-query";
import { Archive, Database, HardDrive, RefreshCcw } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { ErrorState, GlobalFilterBar, KpiCard, PageHeader, Panel, Skeleton, StaleWarning } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { pollingInterval } from "../query/policy";

export function OperationsPage() {
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const result = useQuery({ queryKey: ["ingest-summary", time.query], queryFn: ({ signal }) => api.ingestSummary(time.query, signal), enabled: time.valid, staleTime: 15_000, refetchInterval: pollingInterval(15_000) });
  return <div className="page-stack">
    <PageHeader eyebrow="COLLECTION HEALTH" title="Operations" description="Ingest, failure, and storage lifecycle health from existing Backend projections." actions={<Link className="button" to="/operations/archives"><Archive aria-hidden="true" size={16} />Archive operations</Link>} />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}><TimeFilterFields params={params} setParams={setParams} /></GlobalFilterBar>
    {result.isPending ? <Skeleton rows={8} /> : null}
    {result.error && !result.data ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.isRefetchError && result.data ? <StaleWarning error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <OperationsContent data={result.data.data} /> : null}
  </div>;
}

function OperationsContent({ data }: { data: import("../contracts").IngestSummaryDto }) {
  return <>
    <section className="kpi-grid operations-kpis">
      <KpiCard detail={`Latest ${formatDateTime(data.events.latestIngestedAt)}`} icon={<Database size={18} />} label="Ingested events" value={data.events.ingestedCount} />
      <KpiCard detail={`Oldest ${formatDateTime(data.eventFailures.oldestFailedAt)}`} icon={<RefreshCcw size={18} />} label="Failed" tone={data.eventFailures.failedCount ? "critical" : "neutral"} value={data.eventFailures.failedCount} />
      <KpiCard detail="Successfully replayed by CLI" icon={<RefreshCcw size={18} />} label="Reprocessed" value={data.eventFailures.reprocessedCount} />
      <KpiCard detail="CLI reprocess failures" icon={<RefreshCcw size={18} />} label="Reprocess failed" tone={data.eventFailures.reprocessFailedCount ? "warning" : "neutral"} value={data.eventFailures.reprocessFailedCount} />
    </section>
    <Panel title="Storage lifecycle" subtitle="Current ingest_metadata counts"><section className="storage-grid">
      <StorageCount label="ClickHouse HOT" value={data.storage.clickhouseHotBucketCount} />
      <StorageCount label="RESTORED" value={data.storage.restoredBucketCount} />
      <StorageCount label="ARCHIVED" value={data.storage.glacierArchivedBucketCount} />
      <StorageCount label="RESTORE REQUESTED" value={data.storage.restoringBucketCount} />
      <StorageCount label="RESTORE FAILED" value={data.storage.failedBucketCount} />
      <StorageCount label="EXPIRED" value={data.storage.expiredBucketCount} />
    </section></Panel>
    <Panel title="Operational boundary" subtitle="Failure replay remains CLI-only"><div className="boundary-note"><HardDrive aria-hidden="true" size={22} /><div><strong>No DLQ Monitor or web replay controls</strong><p>This screen intentionally exposes only contracted summary counts and Archive lifecycle actions.</p></div></div></Panel>
  </>;
}

function StorageCount({ label, value }: { label: string; value: number }) {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}
