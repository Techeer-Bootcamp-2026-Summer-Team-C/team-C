import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArchiveRestore } from "lucide-react";
import { useId, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { DataTable, EmptyState, Field, FilterBar, PageHeader, Pagination, Panel, QueryFeedback, StatusPill } from "../components/ui";
import type { ArchiveBucketDto, ArchiveRestoreListQuery, ArchiveRestoreRequest } from "../contracts";
import { archiveLifecycleCounts } from "../features/intelligenceOperations";
import { appliedFilterDescriptors, hasInvalidPagination, removeListFilter } from "../features/listInteractions";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime } from "../lib/format";
import { localDateTimeValue, numberParam, updateParams, utcFromLocal } from "../lib/url";
import { canMutate } from "../query/policy";

export function ArchivesPage() {
  const { t, dateLocale } = useI18n();
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const rawEndpointIds = params.get("endpointIds") ?? "";
  const endpointIds = parseEndpointIds(rawEndpointIds);
  const endpointIdsValid = Boolean(rawEndpointIds) && rawEndpointIds.split(",").every((token) => /^\s*[1-9]\d*\s*$/.test(token));
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const hasCriteria = Boolean(rawEndpointIds || from || to);
  const validRange = Boolean(from && to && Date.parse(from) < Date.parse(to) && Date.parse(to) - Date.parse(from) <= 31 * 86_400_000);
  const ready = endpointIdsValid && endpointIds.length > 0 && validRange && !hasInvalidPagination(params);
  const invalid = hasCriteria && !ready;
  const query: ArchiveRestoreListQuery = { endpointIds, from, to, page: numberParam(params, "page", 1), size: numberParam(params, "size", 50) };
  const result = useQuery({ queryKey: ["archives", query], queryFn: ({ signal }) => api.archives(query, signal), enabled: ready, staleTime: 10_000 });
  const mutation = useMutation({ mutationFn: (request: ArchiveRestoreRequest) => api.startRestore(request), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["archives"] }); } });
  const writeAllowed = auth.user ? canMutate(auth.user.role) : false;
  const appliedFilters = appliedFilterDescriptors(params, [{ key: "endpointIds", label: t("filter.endpointIds") }, { key: "from", label: t("filter.from") }, { key: "to", label: t("filter.to") }]);

  return <div className="page-stack archives-page">
    <Link className="back-link" to="/operations"><ArrowLeft aria-hidden="true" size={15} />{t("navigation.operations")}</Link>
    <PageHeader title={t("archive.title")} />
    <FilterBar appliedFilters={appliedFilters} hasFilters={appliedFilters.length > 0} onClear={() => setParams({})} onRemoveFilter={(key) => setParams(removeListFilter(params, key))} primary={<><Field label={t("filter.endpointIds")}><input aria-describedby="endpoint-id-help" onChange={(event) => setParams(updateParams(params, { endpointIds: event.target.value }))} placeholder="1001, 1002" value={rawEndpointIds} /><small id="endpoint-id-help">{t("archive.endpointHelp")}</small></Field><ArchiveDateTimeField dateLocale={dateLocale} label={t("filter.from")} onCommit={(value) => setParams(updateParams(params, { from: value }))} timestamp={from} /><ArchiveDateTimeField dateLocale={dateLocale} label={t("filter.to")} onCommit={(value) => setParams(updateParams(params, { to: value }))} timestamp={to} /></>} />
    <ArchiveReadinessLedger endpointCount={endpointIds.length} from={from} hasCriteria={hasCriteria} ready={ready} to={to} />
    {hasCriteria ? <QueryFeedback error={result.error} fetching={result.isFetching} hasData={Boolean(result.data)} invalid={invalid} invalidMessage={t("archive.chooseRangeDescription")} onRetry={() => void result.refetch()} pending={result.isPending && ready} refetchError={result.isRefetchError} rows={7} /> : null}
    {ready && result.data ? <ArchiveLifecycleBoard items={result.data.data.items} /> : null}
    {ready && writeAllowed ? <Panel title={t("archive.temporaryRestore")} subtitle={t("archive.policy")}><button className="button primary" disabled={mutation.isPending} onClick={() => mutation.mutate({ endpointIds, from, to })} type="button"><ArchiveRestore aria-hidden="true" size={16} />{mutation.isPending ? t("archive.starting") : t("archive.start")}</button>{mutation.isSuccess ? <p className="mutation-success" role="status">{t("archive.successRequested")}</p> : null}{mutation.error ? <QueryFeedback error={mutation.error} fetching={false} hasData={false} onRetry={() => mutation.reset()} pending={false} /> : null}</Panel> : null}
    {ready && !writeAllowed ? <Panel title={t("archive.access")} subtitle={t("archive.viewerSubtitle")}><p className="read-only-note">{t("archive.viewerDescription")}</p></Panel> : null}
    {ready && result.data ? <Panel title={t("archive.buckets")} subtitle={t("archive.records", { total: result.data.data.total })}>{result.data.data.items.length ? <><DataTable busy={result.isFetching} label={t("archive.buckets")}><thead><tr><th scope="col">Endpoint</th><th aria-sort="descending" scope="col">{t("archive.bucket")}</th><th scope="col">{t("filter.status")}</th><th scope="col">{t("archive.objectPath")}</th><th scope="col">{t("archive.eventCount")}</th><th scope="col">{t("archive.restoreWindow")}</th><th scope="col">{t("archive.lastError")}</th></tr></thead><tbody>{result.data.data.items.map((bucket) => <tr className={`archive-row tone-${bucket.storageStatus.toLowerCase()}`} key={`${bucket.endpointId}-${bucket.bucketStartAt}`}><td><Link to={`/endpoints/${bucket.endpointId}`}>{bucket.endpointId}</Link></td><td>{formatDateTime(bucket.bucketStartAt)}<small>{t("common.to")} {formatDateTime(bucket.bucketEndAt)}</small></td><td><StatusPill value={bucket.storageStatus} /><small>{bucket.storageClass}</small></td><td><code className="path-value">{bucket.storagePath}</code></td><td>{bucket.eventCount}</td><td>{bucket.restoreRequestedAt ? t("archive.requested", { time: formatDateTime(bucket.restoreRequestedAt) }) : t("archive.notRequested")}<small>{bucket.restoreExpiresAt ? t("archive.expires", { time: formatDateTime(bucket.restoreExpiresAt) }) : t("archive.noExpiry")}</small></td><td>{bucket.lastError ?? t("common.none")}</td></tr>)}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title={t("archive.noBuckets")} message={t("archive.noBucketsDescription")} />}</Panel> : null}
  </div>;
}

function ArchiveDateTimeField({ dateLocale, label, onCommit, timestamp }: { dateLocale: string; label: string; onCommit: (value: string | null) => void; timestamp: string }) {
  if (dateLocale !== "en-US") {
    return <Field label={label}><input lang={dateLocale} onChange={(event) => onCommit(event.target.value ? utcFromLocal(event.target.value) : null)} type="datetime-local" value={timestamp ? localDateTimeValue(timestamp) : ""} /></Field>;
  }

  return <EnglishArchiveDateTimeField key={timestamp || "empty"} label={label} onCommit={onCommit} timestamp={timestamp} />;
}

function EnglishArchiveDateTimeField({ label, onCommit, timestamp }: { label: string; onCommit: (value: string | null) => void; timestamp: string }) {
  const { t } = useI18n();
  const errorId = useId();
  const [invalid, setInvalid] = useState(false);
  const commit = (value: string) => {
    if (!value.trim()) {
      setInvalid(false);
      onCommit(null);
      return;
    }
    const parsed = utcFromArchiveText(value);
    if (!parsed) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    onCommit(parsed);
  };

  return <label className={`field ${invalid ? "invalid" : ""}`}>
    <span>{label}</span>
    <input
    aria-describedby={invalid ? errorId : undefined}
    aria-invalid={invalid || undefined}
    defaultValue={timestamp ? localDateTimeValue(timestamp).replace("T", " ") : ""}
    inputMode="numeric"
    lang="en-US"
    onBlur={(event) => commit(event.currentTarget.value)}
    onChange={() => setInvalid(false)}
    onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }}
    pattern={"\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}"}
    placeholder="YYYY-MM-DD HH:mm"
    title="YYYY-MM-DD HH:mm"
    type="text"
    />
    {invalid ? <small className="field-error" id={errorId}>{t("archive.invalidDateTime")}</small> : null}
  </label>;
}

function utcFromArchiveText(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/.exec(trimmed);
  if (!match) return null;
  const localValue = `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}`;
  const parsed = new Date(localValue);
  if (Number.isNaN(parsed.getTime()) || localDateTimeValue(parsed.toISOString()) !== localValue) return null;
  return utcFromLocal(localValue);
}

export function ArchiveReadinessLedger({ endpointCount, from, hasCriteria, ready, to }: { endpointCount: number; from: string; hasCriteria: boolean; ready: boolean; to: string }) {
  const { t } = useI18n();
  return <section aria-label={t("archive.readiness")} className="archive-readiness-ledger">
    <header><div><span>{t("archive.readiness")}</span><strong>{ready ? t("archive.scopeReady") : t("archive.chooseRange")}</strong></div><span className={ready ? "archive-readiness-state ready" : "archive-readiness-state"}>{ready ? t("archive.valid") : t("archive.incomplete")}</span></header>
    <div className="archive-readiness-row"><div><strong>{t("archive.queryScope")}</strong><small>{t("archive.requiredInput")}</small></div><dl><div><dt>{t("filter.endpointIds")}</dt><dd>{endpointCount ? t("archive.endpointCount", { count: endpointCount }) : t("archive.endpointRequirement")}</dd></div><div><dt>{t("archive.utcRange")}</dt><dd>{from && to ? `${formatDateTime(from)} — ${formatDateTime(to)}` : t("archive.rangeRequirement")}</dd></div></dl></div>
    <div className="archive-readiness-row"><div><strong>{t("archive.restorePolicy")}</strong><small>{t("archive.actionBoundary")}</small></div><dl><div><dt>{t("archive.retrieval")}</dt><dd>Glacier Flexible Retrieval</dd></div><div><dt>{t("archive.temporaryCopy")}</dt><dd>{t("archive.standardSevenDays")}</dd></div></dl></div>
    <div className="archive-readiness-row"><div><strong>{t("archive.nextStep")}</strong><small>{t("archive.validationGated")}</small></div><p>{ready ? t("archive.readyDescription") : hasCriteria ? t("archive.invalidScopeDescription") : t("archive.chooseRangeDescription")}</p></div>
  </section>;
}

export function ArchiveLifecycleBoard({ items }: { items: readonly ArchiveBucketDto[] }) {
  const { t } = useI18n();
  const counts = archiveLifecycleCounts(items);
  return <Panel className="archive-lifecycle-panel" title={t("archive.lifecycle")} subtitle={t("archive.lifecycleSubtitle")}>
    <ol aria-label={t("archive.lifecycle")} className="archive-lifecycle">
      {counts.map(({ status, count }) => <li className={`tone-${status.toLowerCase()}`} key={status}><span>{status}</span><strong>{count}</strong><small>{lifecycleDescription(status, t)}</small></li>)}
    </ol>
  </Panel>;
}

function lifecycleDescription(status: ArchiveBucketDto["storageStatus"], t: ReturnType<typeof useI18n>["t"]): string {
  const keys = {
    HOT: "archive.lifecycleHot",
    ARCHIVED: "archive.lifecycleArchived",
    RESTORE_REQUESTED: "archive.lifecycleRequested",
    RESTORED: "archive.lifecycleRestored",
    RESTORE_FAILED: "archive.lifecycleFailed",
    EXPIRED: "archive.lifecycleExpired",
  } as const;
  return t(keys[status]);
}
function parseEndpointIds(value: string): number[] {
  return [...new Set(value.split(",").map((token) => Number(token.trim())).filter((parsed) => Number.isInteger(parsed) && parsed > 0))];
}
