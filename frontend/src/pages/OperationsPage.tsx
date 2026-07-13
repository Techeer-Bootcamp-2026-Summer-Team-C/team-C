import { useQuery } from "@tanstack/react-query";
import { Activity, Archive, Cloud, Database, HardDrive, Radio, RefreshCcw, Server } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, KpiCard, PageHeader, Pagination, Panel, Skeleton, StaleWarning, StatusPill } from "../components/ui";
import type { FailureListQuery, IngestSummaryDto, OperationsHealthDto, ServiceHealthDto } from "../contracts";
import { formatDateTime, humanize } from "../lib/format";
import { allowedValue } from "../lib/params";
import { numberParam, updateParams } from "../lib/url";
import { pollingInterval } from "../query/policy";

export function OperationsPage() {
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const ingest = useQuery({ queryKey: ["ingest-summary", time.query], queryFn: ({ signal }) => api.ingestSummary(time.query, signal), enabled: time.valid, staleTime: 15_000, refetchInterval: pollingInterval(15_000) });
  const health = useQuery({ queryKey: ["operations-health"], queryFn: ({ signal }) => api.operationsHealth(signal), staleTime: 15_000, refetchInterval: pollingInterval(30_000) });
  const failureStatus = allowedValue(params.get("failureStatus"), ["FAILED", "REPROCESSED", "REPROCESS_FAILED"] as const);
  const retryable = allowedValue(params.get("retryable"), ["true", "false"] as const);
  const failureQuery: FailureListQuery = { ...time.query, page: numberParam(params, "page", 1), size: 50, sortOrder: "desc" };
  if (failureStatus) failureQuery.status = failureStatus;
  const failureStage = params.get("failureStage");
  if (failureStage) failureQuery.failureStage = failureStage;
  if (retryable) failureQuery.retryable = retryable === "true";
  const failures = useQuery({ queryKey: ["event-failures", failureQuery], queryFn: ({ signal }) => api.failures(failureQuery, signal), enabled: time.valid, staleTime: 15_000, refetchInterval: pollingInterval(30_000) });
  const refreshing = ingest.isFetching || health.isFetching || failures.isFetching;
  const refresh = () => void Promise.all([ingest.refetch(), health.refetch(), failures.refetch()]);
  return <div className="page-stack">
    <PageHeader eyebrow="COLLECTION HEALTH" title="Operations" description="Live dependency probes, Kafka worker lag, ingest freshness, and storage lifecycle." actions={<>
      <button className="button ghost" disabled={refreshing} onClick={refresh} type="button"><RefreshCcw aria-hidden="true" size={16} />{refreshing ? "Refreshing" : "Refresh live state"}</button>
      <Link className="button" to="/operations/archives"><Archive aria-hidden="true" size={16} />Archive operations</Link>
    </>} />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}><TimeFilterFields params={params} setParams={setParams} />
      <Field label="Failure status"><select onChange={(event) => setParams(updateParams(params, { failureStatus: event.target.value, page: null }))} value={failureStatus ?? ""}><option value="">All statuses</option><option>FAILED</option><option>REPROCESSED</option><option>REPROCESS_FAILED</option></select></Field>
      <Field label="Stage"><input onChange={(event) => setParams(updateParams(params, { failureStage: event.target.value, page: null }))} placeholder="detection" value={params.get("failureStage") ?? ""} /></Field>
      <Field label="Retryable"><select onChange={(event) => setParams(updateParams(params, { retryable: event.target.value, page: null }))} value={retryable ?? ""}><option value="">All</option><option value="true">Retryable</option><option value="false">Not retryable</option></select></Field>
    </GlobalFilterBar>

    {health.isPending ? <Skeleton rows={5} /> : null}
    {health.error && !health.data ? <ErrorState error={health.error} onRetry={() => void health.refetch()} /> : null}
    {health.isRefetchError && health.data ? <StaleWarning error={health.error} onRetry={() => void health.refetch()} /> : null}
    {health.data ? <LiveHealth data={health.data.data} /> : null}

    {ingest.isPending ? <Skeleton rows={8} /> : null}
    {ingest.error && !ingest.data ? <ErrorState error={ingest.error} onRetry={() => void ingest.refetch()} /> : null}
    {ingest.isRefetchError && ingest.data ? <StaleWarning error={ingest.error} onRetry={() => void ingest.refetch()} /> : null}
    {ingest.data ? <IngestContent data={ingest.data.data} /> : null}
    {failures.isPending ? <Skeleton rows={8} /> : null}
    {failures.error && !failures.data ? <ErrorState error={failures.error} onRetry={() => void failures.refetch()} /> : null}
    {failures.data ? <Panel title="Failure queue" subtitle="Read-only DLQ monitor; replay remains CLI-only" meta={<StatusPill value="READ ONLY" />}>
      {failures.data.data.items.length ? <><DataTable label="Event failure queue"><thead><tr><th scope="col">Failure</th><th scope="col">Stage</th><th scope="col">Status</th><th scope="col">Retry</th><th scope="col">Error</th><th scope="col">Failed at</th></tr></thead><tbody>{failures.data.data.items.map((failure) => <tr key={failure.failureId}><td><code className="table-code">{failure.failureId}</code><small>Endpoint {failure.endpointId} · offset {failure.sourcePartition}:{failure.sourceOffset}</small></td><td>{humanize(failure.failureStage)}<small>{failure.consumerName}</small></td><td><StatusPill value={failure.status} /></td><td>{failure.retryable ? "Retryable" : "No"}<small>{failure.retryCount} attempt(s)</small></td><td><strong>{failure.failureCode ?? "Uncoded"}</strong><small>{failure.errorMessage}</small></td><td>{formatDateTime(failure.failedAt)}</td></tr>)}</tbody></DataTable><Pagination page={failures.data.data} /></> : <EmptyState title="No failure rows" message="No Event failures match the current filters." />}
    </Panel> : null}
  </div>;
}

function LiveHealth({ data }: { data: OperationsHealthDto }) {
  return <>
    <section className={`health-summary tone-${data.status.toLowerCase()}`} aria-live="polite">
      <div><Radio aria-hidden="true" size={18} /><span>Live control plane</span><StatusPill value={data.status} /></div>
      <small>Checked {formatDateTime(data.checkedAt)} · refreshes every 30 seconds while this tab is visible</small>
    </section>
    <Panel title="Service health" subtitle="On-demand probes; no historical status is stored">
      <section className="service-health-grid">
        {data.services.map((service) => <ServiceCard key={service.service} service={service} />)}
      </section>
    </Panel>
    <Panel title="Pipeline workers" subtitle="Kafka consumer membership and current committed-offset lag">
      <DataTable label="Pipeline worker health"><thead><tr><th scope="col">Worker</th><th scope="col">Topic</th><th scope="col">Status</th><th scope="col">Members</th><th scope="col">Lag</th><th scope="col">Broker state</th></tr></thead><tbody>
        {data.workers.map((worker) => <tr key={worker.groupId}><td><strong>{worker.worker}</strong><code className="table-code">{worker.groupId}</code></td><td><code>{worker.topic}</code></td><td><StatusPill value={worker.status} /></td><td>{worker.memberCount ?? "Unknown"}</td><td>{worker.lag ?? "Unknown"}</td><td>{worker.detail}</td></tr>)}
      </tbody></DataTable>
    </Panel>
  </>;
}

function ServiceCard({ service }: { service: ServiceHealthDto }) {
  const icons: Record<string, ReactNode> = {
    "Backend API": <Server size={18} />, PostgreSQL: <Database size={18} />, ClickHouse: <Activity size={18} />,
    Kafka: <Radio size={18} />, S3: <Cloud size={18} />,
  };
  return <article className={`service-card tone-${service.status.toLowerCase()}`}>
    <div><span className="service-icon">{icons[service.service] ?? <Server size={18} />}</span><StatusPill value={service.status} /></div>
    <strong>{service.service}</strong>
    <span>{service.latencyMs} ms</span>
    <small>{service.detail}</small>
  </article>;
}

function IngestContent({ data }: { data: IngestSummaryDto }) {
  return <>
    <section className="kpi-grid operations-kpis">
      <KpiCard detail={`${data.events.ratePerMinute.toFixed(2)}/min · ${freshness(data.events.latestIngestedAt)}`} icon={<Database size={18} />} label="Ingested events" value={data.events.ingestedCount} />
      <KpiCard detail={`${data.eventFailures.ratePerMinute.toFixed(2)}/min · Oldest ${formatDateTime(data.eventFailures.oldestFailedAt)}`} icon={<RefreshCcw size={18} />} label="Failed" tone={data.eventFailures.failedCount ? "critical" : "neutral"} value={data.eventFailures.failedCount} />
      <KpiCard detail="Successfully reprocessed by administrator CLI" icon={<RefreshCcw size={18} />} label="Reprocessed" value={data.eventFailures.reprocessedCount} />
      <KpiCard detail="Administrator CLI reprocess failures" icon={<RefreshCcw size={18} />} label="Reprocess failed" tone={data.eventFailures.reprocessFailedCount ? "warning" : "neutral"} value={data.eventFailures.reprocessFailedCount} />
    </section>
    <Panel title="Storage lifecycle" subtitle="Current ingest_metadata counts"><section className="storage-grid">
      <StorageCount label="ClickHouse HOT" value={data.storage.clickhouseHotBucketCount} />
      <StorageCount label="RESTORED" value={data.storage.restoredBucketCount} />
      <StorageCount label="ARCHIVED" value={data.storage.glacierArchivedBucketCount} />
      <StorageCount label="RESTORE REQUESTED" value={data.storage.restoringBucketCount} />
      <StorageCount label="RESTORE FAILED" value={data.storage.failedBucketCount} />
      <StorageCount label="EXPIRED" value={data.storage.expiredBucketCount} />
    </section></Panel>
    <Panel title="Operational boundary" subtitle="Read-only monitoring"><div className="boundary-note"><HardDrive aria-hidden="true" size={22} /><div><strong>No web replay controls were added</strong><p>Failure counts remain visible, while replay continues through the existing administrator CLI.</p></div></div></Panel>
  </>;
}

function freshness(timestamp: string | null): string {
  if (!timestamp) return "No event has been ingested in this range";
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(timestamp)) / 60_000));
  return `Latest ${formatDateTime(timestamp)} · ${minutes}m ago`;
}

function StorageCount({ label, value }: { label: string; value: number }) {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}
