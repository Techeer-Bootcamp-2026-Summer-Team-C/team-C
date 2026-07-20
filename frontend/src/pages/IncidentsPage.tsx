import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { DataTable, EmptyState, Field, FilterBar, PageHeader, Pagination, Panel, QueryFeedback, SortableHeader, StatusPill } from "../components/ui";
import type { IncidentListQuery } from "../contracts";
import { appliedFilterDescriptors, hasInvalidEnum, hasInvalidPagination, hasInvalidPositiveInteger, isSelected, removeListFilter, selectedSearch } from "../features/listInteractions";
import { useI18n } from "../i18n/LocaleContext";
import { detectionTitle } from "../i18n/detectionCopy";
import { formatDateTime, humanize } from "../lib/format";
import { allowedValue, positiveInteger } from "../lib/params";
import { numberParam, updateParams } from "../lib/url";

const STATUSES = ["OPEN", "CLOSED"] as const;
const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;

export function IncidentsPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const status = allowedValue(params.get("status"), STATUSES);
  const severity = allowedValue(params.get("severity"), SEVERITIES);
  const sortOrder = allowedValue(params.get("sortOrder"), ["asc", "desc"] as const) ?? "desc";
  const endpointId = positiveInteger(params.get("endpointId"));
  const invalid = !time.valid || hasInvalidEnum(params, "status", STATUSES) || hasInvalidEnum(params, "severity", SEVERITIES) || hasInvalidEnum(params, "sortOrder", ["asc", "desc"]) || hasInvalidPositiveInteger(params, "endpointId") || hasInvalidPagination(params);
  const query: IncidentListQuery = { ...time.query, page: numberParam(params, "page", 1), size: numberParam(params, "size", 50), sortOrder };
  if (status) query.status = status;
  if (severity) query.severity = severity;
  if (endpointId) query.endpointId = endpointId;
  const result = useQuery({ queryKey: ["incidents", query], queryFn: ({ signal }) => api.incidents(query, signal), enabled: !invalid });
  const appliedFilters = appliedFilterDescriptors(params, [
    { key: "timePreset", label: t("filter.timeRange"), format: humanize }, { key: "from", label: t("filter.from") }, { key: "to", label: t("filter.to") },
    { key: "status", label: t("filter.status"), format: humanize }, { key: "severity", label: t("filter.severity"), format: humanize },
    { key: "endpointId", label: t("filter.endpointId") }, { key: "sortOrder", label: t("filter.order"), format: humanize },
  ]);
  const toggleOrder = () => setParams(updateParams(params, { sortOrder: sortOrder === "desc" ? "asc" : "desc" }));

  return <div className="page-stack">
    <PageHeader title={t("incident.title")} />
    <FilterBar advanced={<><Field label={t("filter.endpointId")}><input inputMode="numeric" onChange={(event) => setParams(updateParams(params, { endpointId: event.target.value }))} value={params.get("endpointId") ?? ""} /></Field><Field label={t("filter.order")}><select onChange={(event) => setParams(updateParams(params, { sortOrder: event.target.value }))} value={sortOrder}><option value="desc">{t("filter.newestFirst")}</option><option value="asc">{t("filter.oldestFirst")}</option></select></Field></>} appliedFilters={appliedFilters} hasFilters={appliedFilters.length > 0} onClear={() => setParams({})} onRemoveFilter={(key) => setParams(removeListFilter(params, key))} primary={<><TimeFilterFields params={params} setParams={setParams} /><Field label={t("filter.status")}><select onChange={(event) => setParams(updateParams(params, { status: event.target.value }))} value={status ?? ""}><option value="">{t("filter.allStatuses")}</option>{STATUSES.map((value) => <option key={value}>{value}</option>)}</select></Field><Field label={t("filter.severity")}><select onChange={(event) => setParams(updateParams(params, { severity: event.target.value }))} value={severity ?? ""}><option value="">{t("filter.allSeverities")}</option>{SEVERITIES.map((value) => <option key={value}>{value}</option>)}</select></Field></>} />
    <QueryFeedback error={result.error} fetching={result.isFetching} hasData={Boolean(result.data)} invalid={invalid} onRetry={() => void result.refetch()} pending={result.isPending && !invalid} refetchError={result.isRefetchError} rows={7} />
    {!invalid && result.data ? <Panel title={t("incident.queue")} subtitle={t("incident.records", { total: result.data.data.total })}>{result.data.data.items.length ? <><DataTable busy={result.isFetching} label={t("incident.queue")}><thead><tr><th scope="col">{t("incident.singular")}</th><th scope="col">Endpoint</th><th scope="col">{t("filter.severity")}</th><th scope="col">{t("filter.status")}</th><th scope="col">{t("incident.alerts")}</th><th scope="col">{t("incident.window")}</th><SortableHeader active direction={sortOrder} label={t("incident.lastDetected")} onSort={toggleOrder} /></tr></thead><tbody>{result.data.data.items.map((incident) => {
      const selected = isSelected(params, incident.incidentId);
      const title = detectionTitle(t, incident.title);
      return <tr className={selected ? "selected-row" : undefined} key={incident.incidentId}><td><Link aria-current={selected ? "true" : undefined} className="table-primary" title={title} to={{ pathname: `/incidents/${incident.incidentId}`, search: selectedSearch(params, incident.incidentId) }}><strong>{title}</strong><code>{incident.correlationKey}</code></Link></td><td><Link to={`/endpoints/${incident.endpointId}`}>{incident.endpointId}</Link></td><td><StatusPill value={incident.severity} /></td><td><StatusPill value={incident.status} /></td><td>{incident.alertCount}</td><td>{formatDateTime(incident.windowStartAt)}<small>{t("common.to")} {formatDateTime(incident.windowEndAt)}</small></td><td>{formatDateTime(incident.lastDetectedAt)}</td></tr>;
    })}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState actions={<><button className="button ghost" disabled={!appliedFilters.length} onClick={() => setParams({})} type="button">{t("filter.clear")}</button><button className="button primary" onClick={() => setParams(updateParams(params, { timePreset: "LATEST_7D", from: null, to: null, page: null }))} type="button">{t("filter.latest7Days")}</button></>} compact message={appliedFilters.length ? t("incident.noFilterMatch") : t("incident.noneInRange")} title={t("incident.noResults")} />}</Panel> : null}
  </div>;
}
