import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArchiveRestore } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, PageHeader, Pagination, Panel, Skeleton, StaleWarning, StatusPill } from "../components/ui";
import type { ArchiveRestoreListQuery, ArchiveRestoreRequest } from "../contracts";
import { formatDateTime } from "../lib/format";
import { localDateTimeValue, numberParam, updateParams, utcFromLocal } from "../lib/url";
import { archivePollingInterval, canMutate } from "../query/policy";

export function ArchivesPage() {
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
    <Link className="back-link" to="/operations"><ArrowLeft aria-hidden="true" size={15} />Operations</Link>
    <PageHeader eyebrow="STORAGE LIFECYCLE" title="Archive operations" description="Query Glacier Flexible Retrieval buckets and start temporary 7-day Standard retrieval." />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}>
      <Field label="Endpoint IDs"><input aria-describedby="endpoint-id-help" onChange={(event) => setParams(updateParams(params, { endpointIds: event.target.value }))} placeholder="1001, 1002" value={params.get("endpointIds") ?? ""} /><small id="endpoint-id-help">Comma-separated positive IDs</small></Field>
      <Field label="From"><input onChange={(event) => setParams(updateParams(params, { from: event.target.value ? utcFromLocal(event.target.value) : null }))} type="datetime-local" value={from ? localDateTimeValue(from) : ""} /></Field>
      <Field label="To"><input onChange={(event) => setParams(updateParams(params, { to: event.target.value ? utcFromLocal(event.target.value) : null }))} type="datetime-local" value={to ? localDateTimeValue(to) : ""} /></Field>
    </GlobalFilterBar>
    {!valid ? <EmptyState title="Choose an Archive range" message="Enter one or more Endpoint IDs and a valid UTC range of at most 31 days. Archive data is not queried until these fields are valid." /> : null}
    {valid && writeAllowed ? <Panel title="Temporary restore" subtitle="Fixed policy: Days 7 · Standard tier"><button className="button primary" disabled={mutation.isPending} onClick={() => mutation.mutate({ endpointIds, from, to })} type="button"><ArchiveRestore aria-hidden="true" size={16} />{mutation.isPending ? "Starting restore…" : "Start archive restore"}</button>{mutation.isSuccess ? <p className="mutation-success" role="status">Restore request processed. Archive status is refreshing.</p> : null}{mutation.error ? <ErrorState error={mutation.error} /> : null}</Panel> : null}
    {valid && !writeAllowed ? <Panel title="Archive access" subtitle="VIEWER access is read-only"><p className="read-only-note">Restore controls are hidden for VIEWER. Current bucket status remains available below.</p></Panel> : null}
    {result.isPending && valid ? <Skeleton rows={7} /> : null}
    {result.error && !result.data ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.isRefetchError && result.data ? <StaleWarning error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <Panel title="Archive buckets" subtitle={`${result.data.data.total} S3 Glacier bucket records`}>
      {result.data.data.items.length ? <><DataTable label="Archive buckets"><thead><tr><th scope="col">Endpoint</th><th scope="col" aria-sort="descending">Bucket</th><th scope="col">Status</th><th scope="col">Object path</th><th scope="col">Events</th><th scope="col">Restore window</th><th scope="col">Last error</th></tr></thead><tbody>{result.data.data.items.map((bucket) => <tr key={`${bucket.endpointId}-${bucket.bucketStartAt}`}><td><Link to={`/endpoints/${bucket.endpointId}`}>{bucket.endpointId}</Link></td><td>{formatDateTime(bucket.bucketStartAt)}<small>to {formatDateTime(bucket.bucketEndAt)}</small></td><td><StatusPill value={bucket.storageStatus} /><small>{bucket.storageClass}</small></td><td><code className="path-value">{bucket.storagePath}</code></td><td>{bucket.eventCount}</td><td>{bucket.restoreRequestedAt ? `Requested ${formatDateTime(bucket.restoreRequestedAt)}` : "Not requested"}<small>{bucket.restoreExpiresAt ? `Expires ${formatDateTime(bucket.restoreExpiresAt)}` : "No active expiry"}</small></td><td>{bucket.lastError ?? "None"}</td></tr>)}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title="No Archive buckets" message="No S3 Glacier buckets overlap this Endpoint and time range." />}
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
