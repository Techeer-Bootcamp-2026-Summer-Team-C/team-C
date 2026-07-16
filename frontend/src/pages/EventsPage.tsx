import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { DataTable, EmptyState, Field, FilterBar, PageHeader, Pagination, Panel, QueryFeedback, SortableHeader, StatusPill } from "../components/ui";
import type { EventListQuery } from "../contracts";
import { eventListSummary } from "../features/eventPresentation";
import { appliedFilterDescriptors, eventDetailSearch, hasInvalidEnum, hasInvalidPagination, hasInvalidPositiveInteger, isSelected, removeListFilter } from "../features/listInteractions";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime, humanize } from "../lib/format";
import { allowedValue, positiveInteger } from "../lib/params";
import { numberParam, stringParam, updateParams } from "../lib/url";

const EVENT_TYPES = ["PROCESS_EXECUTION", "NETWORK_CONNECTION", "FILE_EVENT", "DNS_QUERY", "L7_EVENT"] as const;
const DETAIL_FILTERS = ["processName", "filePath", "domain", "remoteIp", "dnsQuery", "l7Protocol"] as const;

export function EventsPage() {
  const { locale, t } = useI18n();
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const eventType = allowedValue(params.get("eventType"), EVENT_TYPES);
  const sortOrder = allowedValue(params.get("sortOrder"), ["asc", "desc"] as const) ?? "desc";
  const endpointId = positiveInteger(params.get("endpointId"));
  const invalid = !time.valid || hasInvalidEnum(params, "eventType", EVENT_TYPES) || hasInvalidEnum(params, "sortOrder", ["asc", "desc"]) || hasInvalidPositiveInteger(params, "endpointId") || hasInvalidPagination(params);
  const query: EventListQuery = { ...time.query, page: numberParam(params, "page", 1), size: numberParam(params, "size", 50), sortOrder };
  if (eventType) query.eventType = eventType;
  if (endpointId) query.endpointId = endpointId;
  for (const field of DETAIL_FILTERS) {
    const value = stringParam(params, field).trim();
    if (value) query[field] = value;
  }
  const result = useQuery({ queryKey: ["events", query], queryFn: ({ signal }) => api.events(query, signal), enabled: !invalid });
  const appliedFilters = appliedFilterDescriptors(params, [
    { key: "timePreset", label: t("filter.timeRange"), format: humanize }, { key: "from", label: t("filter.from") }, { key: "to", label: t("filter.to") },
    { key: "endpointId", label: t("filter.endpointId") }, { key: "eventType", label: t("events.type"), format: humanize },
    ...DETAIL_FILTERS.map((key) => ({ key, label: eventFilterLabel(key, locale, t) })), { key: "sortOrder", label: t("filter.order"), format: humanize },
  ]);
  const toggleOrder = () => setParams(updateParams(params, { sortOrder: sortOrder === "desc" ? "asc" : "desc" }));

  return <div className="page-stack">
    <PageHeader eyebrow={t("events.eyebrow")} title={t("events.title")} description={t("events.description")} />
    <FilterBar advanced={<>{DETAIL_FILTERS.map((field) => <Field key={field} label={eventFilterLabel(field, locale, t)}><input onChange={(event) => setParams(updateParams(params, { [field]: event.target.value }))} value={params.get(field) ?? ""} /></Field>)}<Field label={t("filter.order")}><select onChange={(event) => setParams(updateParams(params, { sortOrder: event.target.value }))} value={sortOrder}><option value="desc">{t("filter.newestFirst")}</option><option value="asc">{t("filter.oldestFirst")}</option></select></Field></>} appliedFilters={appliedFilters} hasFilters={appliedFilters.length > 0} onClear={() => setParams({})} onRemoveFilter={(key) => setParams(removeListFilter(params, key))} primary={<><TimeFilterFields params={params} setParams={setParams} /><Field label={t("filter.endpointId")}><input inputMode="numeric" onChange={(event) => setParams(updateParams(params, { endpointId: event.target.value }))} value={params.get("endpointId") ?? ""} /></Field><Field label={t("events.type")}><select onChange={(event) => setParams(updateParams(params, { eventType: event.target.value }))} value={eventType ?? ""}><option value="">{t("events.allTypes")}</option>{EVENT_TYPES.map((value) => <option key={value}>{value}</option>)}</select></Field></>} />
    <QueryFeedback error={result.error} fetching={result.isFetching} hasData={Boolean(result.data)} invalid={invalid} onRetry={() => void result.refetch()} pending={result.isPending && !invalid} refetchError={result.isRefetchError} rows={8} />
    {!invalid && result.data ? <Panel title={t("events.stream")} subtitle={t("events.records", { total: result.data.data.total })}>{result.data.data.items.length ? <><DataTable busy={result.isFetching} label={t("events.stream")}><thead><tr><SortableHeader active direction={sortOrder} label={t("events.occurred")} onSort={toggleOrder} /><th scope="col">Endpoint</th><th scope="col">{t("events.type")}</th><th scope="col">{t("events.typeDetail")}</th><th scope="col">{t("events.ingested")}</th></tr></thead><tbody>{result.data.data.items.map((event) => {
      const selected = isSelected(params, event.eventId);
      return <tr className={selected ? "selected-row" : undefined} key={event.eventId}><td><Link aria-current={selected ? "true" : undefined} className="table-primary" to={{ pathname: `/events/${event.eventId}`, search: eventDetailSearch(params, event) }}><strong>{formatDateTime(event.occurredAt)}</strong><code>{event.eventId}</code></Link></td><td><Link to={`/endpoints/${event.endpointId}`}>{event.hostname}</Link><small>ID {event.endpointId}</small></td><td><StatusPill value={event.eventType} /></td><td>{eventListSummary(event) || t("common.notAvailable")}<small>{event.processName && event.eventType !== "PROCESS_EXECUTION" ? event.processName : ""}</small></td><td>{formatDateTime(event.ingestedAt)}</td></tr>;
    })}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title={t("events.noResults")} message={appliedFilters.length ? t("events.noFilterMatch") : t("events.noneInRange")} />}</Panel> : null}
  </div>;
}
function eventFilterLabel(field: typeof DETAIL_FILTERS[number], locale: "EN" | "KO", t: ReturnType<typeof useI18n>["t"]): string {
  if (locale === "EN") return field.replace(/([A-Z])/g, " $1");
  return { processName: t("event.processName"), filePath: t("event.filePath"), domain: "Remote Domain", remoteIp: "Remote IP", dnsQuery: "DNS Query", l7Protocol: "L7 Protocol" }[field];
}
