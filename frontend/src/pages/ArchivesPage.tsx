import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArchiveRestore } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, PageHeader, Pagination, Panel, Skeleton, StaleWarning, StatusPill } from "../components/ui";
import type { ArchiveRestoreListQuery, ArchiveRestoreRequest } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime } from "../lib/format";
import { localDateTimeValue, numberParam, updateParams, utcFromLocal } from "../lib/url";
import { archivePollingInterval, canMutate } from "../query/policy";

export function ArchivesPage() {
  const { t } = useI18n();
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const endpointIds = parseEndpointIds(params.get("endpointIds") ?? "");
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const valid = endpointIds.length > 0 && Boolean(from && to && Date.parse(from) < Date.parse(to) && Date.parse(to) - Date.parse(from) <= 31 * 86_400_000);
  const query: ArchiveRestoreListQuery = { endpointIds, from, to, page: numberParam(params, "page", 1), size: numberParam(params, "size", 50) };
  const result = useQuery({ queryKey: ["archives", query], queryFn: ({ signal }) => api.archives(query, signal), enabled: valid, staleTime: 10_000, refetchInterval: archivePollingInterval });
  const mutation = useMutation({
    mutationFn: (request: ArchiveRestoreRequest) => api.startRestore(request),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["archives"] }); },
  });
  const writeAllowed = auth.user ? canMutate(auth.user.role) : false;

  return <div className="page-stack">
    <Link className="back-link" to="/operations"><ArrowLeft aria-hidden="true" size={15} />{t("navigation.operations")}</Link>
    <PageHeader eyebrow={t("archive.eyebrow")} title={t("archive.title")} description={t("archive.description")} />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}>
      <Field label={t("filter.endpointIds")}><input aria-describedby="endpoint-id-help" onChange={(event) => setParams(updateParams(params, { endpointIds: event.target.value }))} placeholder="1001, 1002" value={params.get("endpointIds") ?? ""} /><small id="endpoint-id-help">{t("archive.endpointHelp")}</small></Field>
      <Field label={t("filter.from")}><input onChange={(event) => setParams(updateParams(params, { from: event.target.value ? utcFromLocal(event.target.value) : null }))} type="datetime-local" value={from ? localDateTimeValue(from) : ""} /></Field>
      <Field label={t("filter.to")}><input onChange={(event) => setParams(updateParams(params, { to: event.target.value ? utcFromLocal(event.target.value) : null }))} type="datetime-local" value={to ? localDateTimeValue(to) : ""} /></Field>
    </GlobalFilterBar>
    {!valid ? <EmptyState title={t("archive.chooseRange")} message={t("archive.chooseRangeDescription")} /> : null}
    {valid && writeAllowed ? <Panel title={t("archive.temporaryRestore")} subtitle={t("archive.policy")}><button className="button primary" disabled={mutation.isPending} onClick={() => mutation.mutate({ endpointIds, from, to })} type="button"><ArchiveRestore aria-hidden="true" size={16} />{mutation.isPending ? t("archive.starting") : t("archive.start")}</button>{mutation.isSuccess ? <p className="mutation-success" role="status">{t("archive.success")}</p> : null}{mutation.error ? <ErrorState error={mutation.error} /> : null}</Panel> : null}
    {valid && !writeAllowed ? <Panel title={t("archive.access")} subtitle={t("archive.viewerSubtitle")}><p className="read-only-note">{t("archive.viewerDescription")}</p></Panel> : null}
    {result.isPending && valid ? <Skeleton rows={7} /> : null}
    {result.error && !result.data ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.isRefetchError && result.data ? <StaleWarning error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <Panel title={t("archive.buckets")} subtitle={t("archive.records", { total: result.data.data.total })}>
      {result.data.data.items.length ? <><DataTable label={t("archive.buckets")}><thead><tr><th scope="col">Endpoint</th><th scope="col" aria-sort="descending">{t("archive.bucket")}</th><th scope="col">{t("filter.status")}</th><th scope="col">{t("archive.objectPath")}</th><th scope="col">{t("archive.eventCount")}</th><th scope="col">{t("archive.restoreWindow")}</th><th scope="col">{t("archive.lastError")}</th></tr></thead><tbody>{result.data.data.items.map((bucket) => <tr key={`${bucket.endpointId}-${bucket.bucketStartAt}`}><td><Link to={`/endpoints/${bucket.endpointId}`}>{bucket.endpointId}</Link></td><td>{formatDateTime(bucket.bucketStartAt)}<small>{t("common.to")} {formatDateTime(bucket.bucketEndAt)}</small></td><td><StatusPill value={bucket.storageStatus} /><small>{bucket.storageClass}</small></td><td><code className="path-value">{bucket.storagePath}</code></td><td>{bucket.eventCount}</td><td>{bucket.restoreRequestedAt ? t("archive.requested", { time: formatDateTime(bucket.restoreRequestedAt) }) : t("archive.notRequested")}<small>{bucket.restoreExpiresAt ? t("archive.expires", { time: formatDateTime(bucket.restoreExpiresAt) }) : t("archive.noExpiry")}</small></td><td>{bucket.lastError ?? t("common.none")}</td></tr>)}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title={t("archive.noBuckets")} message={t("archive.noBucketsDescription")} />}
    </Panel> : null}
  </div>;
}

function parseEndpointIds(value: string): number[] {
  const unique = new Set<number>();
  for (const token of value.split(",")) {
    const parsed = Number(token.trim());
    if (Number.isInteger(parsed) && parsed > 0) unique.add(parsed);
  }
  return [...unique];
}
