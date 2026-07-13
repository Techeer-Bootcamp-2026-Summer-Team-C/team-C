import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, PageHeader, Pagination, Panel, Skeleton, StatusPill } from "../components/ui";
import type { EventListQuery } from "../contracts";
import { formatDateTime, displayNullable } from "../lib/format";
import { allowedValue, positiveInteger } from "../lib/params";
import { numberParam, stringParam, updateParams } from "../lib/url";

export function EventsPage() {
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const eventType = allowedValue(params.get("eventType"), ["PROCESS_EXECUTION", "NETWORK_CONNECTION", "FILE_EVENT", "DNS_QUERY", "L7_EVENT"] as const);
  const sortOrder = allowedValue(params.get("sortOrder"), ["asc", "desc"] as const) ?? "desc";
  const endpointId = positiveInteger(params.get("endpointId"));
  const query: EventListQuery = { ...time.query, page: numberParam(params, "page", 1), size: numberParam(params, "size", 50), sortOrder };
  if (eventType) query.eventType = eventType;
  if (endpointId) query.endpointId = endpointId;
  for (const field of ["processName", "filePath", "domain", "remoteIp", "dnsQuery", "l7Protocol"] as const) {
    const value = stringParam(params, field).trim();
    if (value) query[field] = value;
  }
  const result = useQuery({ queryKey: ["events", query], queryFn: ({ signal }) => api.events(query, signal), enabled: time.valid });
  const archiveNotReady = result.error instanceof ApiError && result.error.code === "ARCHIVE_NOT_READY";

  return <div className="page-stack">
    <PageHeader eyebrow="EVENT EVIDENCE" title="Events" description="HOT ClickHouse and directly read RESTORED Parquet events." />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}>
      <TimeFilterFields params={params} setParams={setParams} />
      <Field label="Endpoint ID"><input inputMode="numeric" onChange={(event) => setParams(updateParams(params, { endpointId: event.target.value }))} value={params.get("endpointId") ?? ""} /></Field>
      <Field label="Event type"><select onChange={(event) => setParams(updateParams(params, { eventType: event.target.value }))} value={eventType ?? ""}><option value="">All types</option><option>PROCESS_EXECUTION</option><option>NETWORK_CONNECTION</option><option>FILE_EVENT</option><option>DNS_QUERY</option><option>L7_EVENT</option></select></Field>
      {(["processName", "filePath", "domain", "remoteIp", "dnsQuery", "l7Protocol"] as const).map((field) => <Field key={field} label={field.replace(/([A-Z])/g, " $1")}><input onChange={(event) => setParams(updateParams(params, { [field]: event.target.value }))} value={params.get(field) ?? ""} /></Field>)}
      <Field label="Order"><select onChange={(event) => setParams(updateParams(params, { sortOrder: event.target.value }))} value={sortOrder}><option value="desc">Newest first</option><option value="asc">Oldest first</option></select></Field>
    </GlobalFilterBar>
    {result.isPending && time.valid ? <Skeleton rows={8} /> : null}
    {result.error ? <ErrorState archiveAction={archiveNotReady} error={result.error} {...(!archiveNotReady ? { onRetry: () => void result.refetch() } : {})} /> : null}
    {result.data ? <Panel title="Event stream" subtitle={`${result.data.data.total} Event records`}>
      {result.data.data.items.length ? <><DataTable label="Event stream"><thead><tr><th scope="col" aria-sort={sortOrder === "desc" ? "descending" : "ascending"}>Occurred</th><th scope="col">Endpoint</th><th scope="col">Type</th><th scope="col">Process</th><th scope="col">Network / DNS / L7</th><th scope="col">Ingested</th></tr></thead><tbody>{result.data.data.items.map((event) => <tr key={event.eventId}><td><Link className="table-primary" to={`/events/${event.eventId}?endpointId=${event.endpointId}&occurredAt=${encodeURIComponent(event.occurredAt)}`}><strong>{formatDateTime(event.occurredAt)}</strong><code>{event.eventId}</code></Link></td><td><Link to={`/endpoints/${event.endpointId}`}>{event.hostname}</Link><small>ID {event.endpointId}</small></td><td><StatusPill value={event.eventType} /></td><td>{displayNullable(event.processName)}<small>{displayNullable(event.commandLine)}</small></td><td>{event.remoteDomain ?? event.remoteIp ?? event.dnsQuery ?? event.l7Protocol ?? "Not available"}</td><td>{formatDateTime(event.ingestedAt)}</td></tr>)}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title="No Events found" message={params.size ? "No Events match the current filters." : "No Events are available in this time range."} />}
    </Panel> : null}
  </div>;
}
