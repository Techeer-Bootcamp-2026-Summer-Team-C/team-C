import { useQuery } from "@tanstack/react-query";
import { Activity, Archive, Cloud, Cpu, Database, HardDrive, MonitorDot, Radio, RefreshCcw, Server, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, KpiCard, PageHeader, Pagination, Panel, PartialFailureWarning, Skeleton, StaleWarning, StatusPill } from "../components/ui";
import type { FailureListQuery, IngestSummaryDto, OperationsHealthDto, ServiceHealthDto } from "../contracts";
import { buildPipelineSnapshot, type PipelineStageId } from "../features/intelligenceOperations";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime, humanize } from "../lib/format";
import { allowedValue } from "../lib/params";
import { numberParam, updateParams } from "../lib/url";
import { pollingInterval } from "../query/policy";

export function OperationsPage() {
  const { t } = useI18n();
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
    <PageHeader eyebrow={t("operations.eyebrow")} title={t("operations.title")} description={t("operations.description")} actions={<>
      <button className="button ghost" disabled={refreshing} onClick={refresh} type="button"><RefreshCcw aria-hidden="true" size={16} />{refreshing ? t("operations.refreshing") : t("operations.refreshLive")}</button>
      <Link className="button" to="/operations/archives"><Archive aria-hidden="true" size={16} />{t("operations.archiveAction")}</Link>
    </>} />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}><TimeFilterFields params={params} setParams={setParams} />
      <Field label={t("operations.failureStatus")}><select onChange={(event) => setParams(updateParams(params, { failureStatus: event.target.value, page: null }))} value={failureStatus ?? ""}><option value="">{t("filter.allStatuses")}</option><option>FAILED</option><option>REPROCESSED</option><option>REPROCESS_FAILED</option></select></Field>
      <Field label={t("operations.stage")}><input onChange={(event) => setParams(updateParams(params, { failureStage: event.target.value, page: null }))} placeholder="detection" value={params.get("failureStage") ?? ""} /></Field>
      <Field label={t("operations.retryable")}><select onChange={(event) => setParams(updateParams(params, { retryable: event.target.value, page: null }))} value={retryable ?? ""}><option value="">{t("operations.all")}</option><option value="true">{t("operations.retryable")}</option><option value="false">{t("operations.notRetryable")}</option></select></Field>
    </GlobalFilterBar>

    {health.isPending ? <Skeleton rows={5} /> : null}
    {health.error && !health.data ? <ErrorState error={health.error} onRetry={() => void health.refetch()} /> : null}
    {health.isRefetchError && health.data ? <StaleWarning error={health.error} onRetry={() => void health.refetch()} /> : null}
    {Boolean(health.error && !health.data) !== Boolean(ingest.error && !ingest.data) ? <PartialFailureWarning message={health.data ? t("operations.ingestPartial") : t("operations.healthPartial")} /> : null}
    {health.data && ingest.data ? <PipelineSnapshot health={health.data.data} ingest={ingest.data.data} /> : null}
    {health.data ? <LiveHealth data={health.data.data} /> : null}

    {ingest.isPending ? <Skeleton rows={8} /> : null}
    {ingest.error && !ingest.data ? <ErrorState error={ingest.error} onRetry={() => void ingest.refetch()} /> : null}
    {ingest.isRefetchError && ingest.data ? <StaleWarning error={ingest.error} onRetry={() => void ingest.refetch()} /> : null}
    {ingest.data ? <IngestContent data={ingest.data.data} /> : null}
    {failures.isPending ? <Skeleton rows={8} /> : null}
    {failures.error && !failures.data ? <ErrorState error={failures.error} onRetry={() => void failures.refetch()} /> : null}
    {failures.data ? <Panel title={t("operations.failureQueue")} subtitle={t("operations.failureQueueSubtitle")} meta={<StatusPill value="READ ONLY" />}>
      {failures.data.data.items.length ? <><DataTable label={t("operations.eventFailureQueue")}><thead><tr><th scope="col">{t("operations.failure")}</th><th scope="col">{t("operations.stage")}</th><th scope="col">{t("filter.status")}</th><th scope="col">{t("operations.retry")}</th><th scope="col">{t("operations.error")}</th><th scope="col">{t("operations.failedAt")}</th></tr></thead><tbody>{failures.data.data.items.map((failure) => <tr key={failure.failureId}><td><code className="table-code">{failure.failureId}</code><small>Endpoint {failure.endpointId} · offset {failure.sourcePartition}:{failure.sourceOffset}</small></td><td>{humanize(failure.failureStage)}<small>{failure.consumerName}</small></td><td><StatusPill value={failure.status} /></td><td>{failure.retryable ? t("operations.retryable") : t("operations.no")}<small>{t("operations.attempts", { count: failure.retryCount })}</small></td><td><strong>{failure.failureCode ?? t("operations.uncoded")}</strong><small>{failure.errorMessage}</small></td><td>{formatDateTime(failure.failedAt)}</td></tr>)}</tbody></DataTable><Pagination page={failures.data.data} /></> : <EmptyState title={t("operations.noFailureRows")} message={t("operations.noFailureRowsDescription")} />}
    </Panel> : null}
  </div>;
}

export function PipelineSnapshot({ health, ingest }: { health: OperationsHealthDto; ingest: IngestSummaryDto }) {
  const { t } = useI18n();
  const stages = buildPipelineSnapshot(health, ingest);
  const totalLag = health.workers.reduce((sum, worker) => sum + (worker.lag ?? 0), 0);
  const details: Record<PipelineStageId, { primary: string; secondary: string }> = {
    COLLECTION: {
      primary: t("operations.collectionEvents", { count: ingest.events.ingestedCount }),
      secondary: ingest.events.latestIngestedAt ? t("operations.collectionLatest", { time: formatDateTime(ingest.events.latestIngestedAt) }) : t("operations.noIngestedInRange"),
    },
    DETECTION: {
      primary: t("operations.detectionWorkers", { count: health.workers.length, lag: totalLag }),
      secondary: t("operations.detectionFailures", { count: ingest.eventFailures.failedCount + ingest.eventFailures.reprocessFailedCount }),
    },
    STORAGE: {
      primary: t("operations.storageBuckets", { count: ingest.storage.clickhouseHotBucketCount + ingest.storage.glacierArchivedBucketCount + ingest.storage.restoredBucketCount }),
      secondary: t("operations.storageExceptions", { restoring: ingest.storage.restoringBucketCount, failed: ingest.storage.failedBucketCount }),
    },
  };
  return <Panel className="pipeline-snapshot-panel" title={t("operations.currentPipelineSnapshot")} subtitle={t("operations.currentPipelineSnapshotSubtitle")} meta={<StatusPill value={health.status} />}>
    <CollectionPath health={health} />
    <div className="pipeline-section-label"><span>{t("operations.problemSummary")}</span><small>{t("operations.problemSummaryDescription")}</small></div>
    <ol aria-label={t("operations.currentPipelineSnapshot")} className="pipeline-snapshot">
      {stages.map((stage) => <li className={`tone-${stage.status.toLowerCase()}`} key={stage.id}>
        <div><span>{t(`operations.stage${stage.id}` as "operations.stageCOLLECTION" | "operations.stageDETECTION" | "operations.stageSTORAGE")}</span><StatusPill value={stage.status} /></div>
        <strong>{details[stage.id].primary}</strong>
        <small>{details[stage.id].secondary}</small>
      </li>)}
    </ol>
    <p className="snapshot-caveat">{t("operations.snapshotCaveat", { time: formatDateTime(health.checkedAt) })}</p>
  </Panel>;
}

export function CollectionPath({ health }: { health: OperationsHealthDto }) {
  const { t } = useI18n();
  const service = (name: string) => health.services.find((item) => item.service === name);
  const worker = (name: string) => health.workers.find((item) => item.worker.toLowerCase().includes(name));
  const backend = service("Backend API");
  const kafka = service("Kafka");
  const clickhouse = service("ClickHouse");
  const postgres = service("PostgreSQL");
  const storageWorker = worker("storage");
  const detectionWorker = worker("detection");
  const nodes = [
    { label: t("operations.pathAgent"), detail: t("operations.noHealthProbe"), status: "NO PROBE", icon: <MonitorDot size={17} /> },
    { label: "Nginx / mTLS", detail: t("operations.noHealthProbe"), status: "NO PROBE", icon: <ShieldCheck size={17} /> },
    { label: t("operations.pathCollector"), detail: backend ? `${backend.latencyMs} ms · ${backend.detail}` : t("operations.noHealthProbe"), status: backend?.status ?? "NO PROBE", icon: <Server size={17} /> },
    { label: "Kafka telemetry.raw", detail: kafka?.detail ?? t("operations.noHealthProbe"), status: kafka?.status ?? "NO PROBE", icon: <Radio size={17} /> },
    { label: t("operations.pathStorageWorker"), detail: workerDetail(storageWorker, t("operations.unknown")), status: storageWorker?.status ?? "NO PROBE", icon: <Cpu size={17} /> },
    { label: "ClickHouse", detail: clickhouse ? `${clickhouse.latencyMs} ms · ${clickhouse.detail}` : t("operations.noHealthProbe"), status: clickhouse?.status ?? "NO PROBE", icon: <Database size={17} /> },
    { label: "Kafka telemetry.validated", detail: kafka?.detail ?? t("operations.noHealthProbe"), status: kafka?.status ?? "NO PROBE", icon: <Radio size={17} /> },
    { label: t("operations.pathDetectionWorker"), detail: workerDetail(detectionWorker, t("operations.unknown")), status: detectionWorker?.status ?? "NO PROBE", icon: <Cpu size={17} /> },
    { label: "PostgreSQL", detail: postgres ? `${postgres.latencyMs} ms · ${postgres.detail}` : t("operations.noHealthProbe"), status: postgres?.status ?? "NO PROBE", icon: <Database size={17} /> },
  ];
  return <section aria-label={t("operations.collectionPath")} className="collection-path-board">
    <header><div><span>{t("operations.collectionPath")}</span><strong>{t("operations.collectionPathSubtitle")}</strong></div><StatusPill value={health.status} /></header>
    <ol>{nodes.map((node, index) => <li className={`tone-${node.status.toLowerCase().replaceAll(" ", "-")}`} key={node.label}>
      <span className="collection-path-index">{String(index + 1).padStart(2, "0")}</span>
      <span className="collection-path-icon" aria-hidden="true">{node.icon}</span>
      <div><strong>{node.label}</strong><small>{node.detail}</small></div>
      <StatusPill value={node.status} />
    </li>)}</ol>
    <p>{t("operations.collectionPathCaveat")}</p>
  </section>;
}

function workerDetail(worker: OperationsHealthDto["workers"][number] | undefined, unknown: string): string {
  if (!worker) return unknown;
  return `${worker.memberCount ?? unknown} member · lag ${worker.lag ?? unknown}`;
}

function LiveHealth({ data }: { data: OperationsHealthDto }) {
  const { t } = useI18n();
  return <>
    <section className={`health-summary tone-${data.status.toLowerCase()}`} aria-live="polite">
      <div><Radio aria-hidden="true" size={18} /><span>{t("operations.liveControlPlane")}</span><StatusPill value={data.status} /></div>
      <small>{t("operations.checked", { time: formatDateTime(data.checkedAt) })}</small>
    </section>
    <Panel title={t("operations.serviceHealth")} subtitle={t("operations.serviceHealthSubtitle")}>
      <section className="service-health-grid">
        {data.services.map((service) => <ServiceCard key={service.service} service={service} />)}
      </section>
    </Panel>
    <Panel title={t("operations.pipelineWorkers")} subtitle={t("operations.pipelineWorkersSubtitle")}>
      <DataTable label={t("operations.pipelineWorkerHealth")}><thead><tr><th scope="col">Worker</th><th scope="col">Topic</th><th scope="col">{t("filter.status")}</th><th scope="col">{t("operations.members")}</th><th scope="col">Lag</th><th scope="col">{t("operations.brokerState")}</th></tr></thead><tbody>
        {data.workers.map((worker) => <tr key={worker.groupId}><td><strong>{worker.worker}</strong><code className="table-code">{worker.groupId}</code></td><td><code>{worker.topic}</code></td><td><StatusPill value={worker.status} /></td><td>{worker.memberCount ?? t("operations.unknown")}</td><td>{worker.lag ?? t("operations.unknown")}</td><td>{worker.detail}</td></tr>)}
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
  const { t } = useI18n();
  const latest = freshness(data.events.latestIngestedAt);
  return <>
    <section className="kpi-grid operations-kpis">
      <KpiCard detail={latest ? t("operations.ingestFreshness", { rate: data.events.ratePerMinute.toFixed(2), time: latest.time, minutes: latest.minutes }) : t("operations.noIngestedInRange")} icon={<Database size={18} />} label={t("operations.ingestedEvents")} value={data.events.ingestedCount} />
      <KpiCard detail={t("operations.failureRate", { rate: data.eventFailures.ratePerMinute.toFixed(2), time: formatDateTime(data.eventFailures.oldestFailedAt) })} icon={<RefreshCcw size={18} />} label={t("operations.failed")} tone={data.eventFailures.failedCount ? "critical" : "neutral"} value={data.eventFailures.failedCount} />
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

function freshness(timestamp: string | null): { time: string; minutes: number } | null {
  if (!timestamp) return null;
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(timestamp)) / 60_000));
  return { time: formatDateTime(timestamp), minutes };
}

function StorageCount({ label, value }: { label: string; value: number }) {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}
