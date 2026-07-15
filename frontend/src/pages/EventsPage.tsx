import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, PageHeader, Pagination, Panel, Skeleton, StatusPill } from "../components/ui";
import type { EventListQuery } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime, displayNullable } from "../lib/format";
import { allowedValue, positiveInteger } from "../lib/params";
import { numberParam, stringParam, updateParams } from "../lib/url";

export function EventsPage() {
  const { locale, t } = useI18n();
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
    <PageHeader eyebrow={t("events.eyebrow")} title={t("events.title")} description={t("events.description")} />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}>
      <TimeFilterFields params={params} setParams={setParams} />
      <Field label={t("filter.endpointId")}><input inputMode="numeric" onChange={(event) => setParams(updateParams(params, { endpointId: event.target.value }))} value={params.get("endpointId") ?? ""} /></Field>
      <Field label={t("events.type")}><select onChange={(event) => setParams(updateParams(params, { eventType: event.target.value }))} value={eventType ?? ""}><option value="">{t("events.allTypes")}</option><option>PROCESS_EXECUTION</option><option>NETWORK_CONNECTION</option><option>FILE_EVENT</option><option>DNS_QUERY</option><option>L7_EVENT</option></select></Field>
      {(["processName", "filePath", "domain", "remoteIp", "dnsQuery", "l7Protocol"] as const).map((field) => <Field key={field} label={eventFilterLabel(field, locale, t)}><input onChange={(event) => setParams(updateParams(params, { [field]: event.target.value }))} value={params.get(field) ?? ""} /></Field>)}
      <Field label={t("filter.order")}><select onChange={(event) => setParams(updateParams(params, { sortOrder: event.target.value }))} value={sortOrder}><option value="desc">{t("filter.newestFirst")}</option><option value="asc">{t("filter.oldestFirst")}</option></select></Field>
    </GlobalFilterBar>
    {result.isPending && time.valid ? <Skeleton rows={8} /> : null}
    {result.error ? <ErrorState archiveAction={archiveNotReady} error={result.error} {...(!archiveNotReady ? { onRetry: () => void result.refetch() } : {})} /> : null}
    {result.data ? <Panel title={t("events.stream")} subtitle={t("events.records", { total: result.data.data.total })}>
      {result.data.data.items.length ? <><DataTable label={t("events.stream")}><thead><tr><th scope="col" aria-sort={sortOrder === "desc" ? "descending" : "ascending"}>{t("events.occurred")}</th><th scope="col">Endpoint</th><th scope="col">{t("events.type")}</th><th scope="col">{t("events.process")}</th><th scope="col">{t("events.network")}</th><th scope="col">{t("events.ingested")}</th></tr></thead><tbody>{result.data.data.items.map((event) => <tr key={event.eventId}><td><Link className="table-primary" to={`/events/${event.eventId}?endpointId=${event.endpointId}&occurredAt=${encodeURIComponent(event.occurredAt)}`}><strong>{formatDateTime(event.occurredAt)}</strong><code>{event.eventId}</code></Link></td><td><Link to={`/endpoints/${event.endpointId}`}>{event.hostname}</Link><small>ID {event.endpointId}</small></td><td><StatusPill value={event.eventType} /></td><td>{displayNullable(event.processName)}<small>{displayNullable(event.commandLine)}</small></td><td>{event.remoteDomain ?? event.remoteIp ?? event.dnsQuery ?? event.l7Protocol ?? t("common.notAvailable")}</td><td>{formatDateTime(event.ingestedAt)}</td></tr>)}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title={t("events.noResults")} message={params.size ? t("events.noFilterMatch") : t("events.noneInRange")} />}
    </Panel> : null}
  </div>;
}

function eventFilterLabel(
  field: "processName" | "filePath" | "domain" | "remoteIp" | "dnsQuery" | "l7Protocol",
  locale: "EN" | "KO",
  t: ReturnType<typeof useI18n>["t"],
): string {
  if (locale === "EN") return field.replace(/([A-Z])/g, " $1");
  const labels = {
    processName: t("event.processName"),
    filePath: t("event.filePath"),
    domain: "Remote Domain",
    remoteIp: "Remote IP",
    dnsQuery: "DNS Query",
    l7Protocol: "L7 Protocol",
  } as const;
  return labels[field];
}
