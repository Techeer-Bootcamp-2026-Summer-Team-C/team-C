import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { DataTable, EmptyState, Field, FilterBar, PageHeader, Pagination, Panel, QueryFeedback, SortableHeader, StatusPill } from "../components/ui";
import type { EndpointListQuery } from "../contracts";
import { appliedFilterDescriptors, hasInvalidEnum, hasInvalidPagination, hasInvalidText, isSelected, removeListFilter, selectedSearch } from "../features/listInteractions";
import { useI18n } from "../i18n/LocaleContext";
import { parseEndpointIds } from "../lib/endpointIds";
import { formatDateTime, humanize } from "../lib/format";
import { allowedValue } from "../lib/params";
import { numberParam, updateParams } from "../lib/url";

const STATUSES = ["ONLINE", "OFFLINE", "RETIRED"] as const;
const OS_TYPES = ["WINDOWS", "MACOS"] as const;
const RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
const SORT_FIELDS = ["riskScore", "lastSeenAt", "registeredAt"] as const;

export function EndpointsPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const status = allowedValue(params.get("status"), STATUSES);
  const osType = allowedValue(params.get("osType"), OS_TYPES);
  const riskLevel = allowedValue(params.get("riskLevel"), RISK_LEVELS);
  const sortBy = allowedValue(params.get("sortBy"), SORT_FIELDS) ?? "riskScore";
  const sortOrder = allowedValue(params.get("sortOrder"), ["asc", "desc"] as const) ?? "desc";
  const rawEndpointIds = params.get("endpointIds") ?? "";
  const endpointIds = parseEndpointIds(rawEndpointIds);
  const q = (params.get("q") ?? "").trim();
  const invalidEndpointIds = Boolean(rawEndpointIds) && rawEndpointIds.split(",").some((token) => !/^\s*[1-9]\d*\s*$/.test(token));
  const invalid = hasInvalidEnum(params, "status", STATUSES) || hasInvalidEnum(params, "osType", OS_TYPES) || hasInvalidEnum(params, "riskLevel", RISK_LEVELS) || hasInvalidEnum(params, "sortBy", SORT_FIELDS) || hasInvalidEnum(params, "sortOrder", ["asc", "desc"]) || hasInvalidText(params, "q", 128) || invalidEndpointIds || hasInvalidPagination(params);
  const query: EndpointListQuery = { page: numberParam(params, "page", 1), size: numberParam(params, "size", 50), sortBy, sortOrder };
  if (q) query.q = q;
  if (status) query.status = status;
  if (osType) query.osType = osType;
  if (riskLevel) query.riskLevel = riskLevel;
  if (endpointIds.length) query.endpointIds = endpointIds;
  const result = useQuery({ queryKey: ["endpoints", query], queryFn: ({ signal }) => api.endpoints(query, signal), enabled: !invalid });
  const appliedFilters = appliedFilterDescriptors(params, [
    { key: "q", label: t("endpoints.search") }, { key: "status", label: t("filter.status"), format: humanize }, { key: "riskLevel", label: t("endpoints.riskLevel"), format: humanize },
    { key: "endpointIds", label: t("filter.endpointIds") }, { key: "osType", label: t("endpoints.operatingSystem"), format: humanize }, { key: "sortBy", label: t("filter.sort"), format: humanize }, { key: "sortOrder", label: t("filter.order"), format: humanize },
  ]);
  const updateSort = (nextSortBy: typeof SORT_FIELDS[number]) => setParams(updateParams(params, { sortBy: nextSortBy, sortOrder: sortBy === nextSortBy && sortOrder === "desc" ? "asc" : "desc" }));

  return <div className="page-stack">
    <PageHeader title={t("endpoints.title")} />
    <FilterBar advanced={<><Field label={t("filter.endpointIds")}><input onChange={(event) => setParams(updateParams(params, { endpointIds: event.target.value }))} placeholder="1, 2, 7" value={rawEndpointIds} /></Field><Field label={t("endpoints.operatingSystem")}><select onChange={(event) => setParams(updateParams(params, { osType: event.target.value }))} value={osType ?? ""}><option value="">{t("endpoints.allSystems")}</option>{OS_TYPES.map((value) => <option key={value}>{value}</option>)}</select></Field><Field label={t("filter.sort")}><select onChange={(event) => setParams(updateParams(params, { sortBy: event.target.value }))} value={sortBy}><option value="riskScore">{t("endpoints.riskScore")}</option><option value="lastSeenAt">{t("endpoints.lastSeen")}</option><option value="registeredAt">{t("endpoints.registered")}</option></select></Field><Field label={t("filter.order")}><select onChange={(event) => setParams(updateParams(params, { sortOrder: event.target.value }))} value={sortOrder}><option value="desc">{t("filter.descending")}</option><option value="asc">{t("filter.ascending")}</option></select></Field></>} appliedFilters={appliedFilters} hasFilters={appliedFilters.length > 0} onClear={() => setParams({})} onRemoveFilter={(key) => setParams(removeListFilter(params, key))} primary={<><Field label={t("endpoints.search")}><input autoComplete="off" onChange={(event) => setParams(updateParams(params, { q: event.target.value }))} placeholder={t("search.placeholder")} value={params.get("q") ?? ""} /></Field><Field label={t("filter.status")}><select onChange={(event) => setParams(updateParams(params, { status: event.target.value }))} value={status ?? ""}><option value="">{t("filter.allStatuses")}</option>{STATUSES.map((value) => <option key={value}>{value}</option>)}</select></Field><Field label={t("endpoints.riskLevel")}><select onChange={(event) => setParams(updateParams(params, { riskLevel: event.target.value }))} value={riskLevel ?? ""}><option value="">{t("endpoints.allLevels")}</option>{RISK_LEVELS.map((value) => <option key={value}>{value}</option>)}</select></Field></>} />
    <QueryFeedback error={result.error} fetching={result.isFetching} hasData={Boolean(result.data)} invalid={invalid} onRetry={() => void result.refetch()} pending={result.isPending && !invalid} refetchError={result.isRefetchError} rows={8} />
    {!invalid && result.data ? <Panel title={t("endpoints.inventory")} subtitle={t("endpoints.records", { total: result.data.data.total })}>{result.data.data.items.length ? <><DataTable busy={result.isFetching} label={t("endpoints.inventory")}><thead><tr><th scope="col">Endpoint</th><th scope="col">{t("endpoints.os")}</th><th scope="col">{t("filter.status")}</th><SortableHeader active={sortBy === "lastSeenAt"} direction={sortOrder} label={t("endpoints.lastSeen")} onSort={() => updateSort("lastSeenAt")} /><SortableHeader active={sortBy === "riskScore"} direction={sortOrder} label={t("endpoints.risk")} onSort={() => updateSort("riskScore")} /><th scope="col">{t("endpoints.activeAlerts")}</th><th scope="col">{t("endpoints.openIncidents")}</th></tr></thead><tbody>{result.data.data.items.map((endpoint) => {
      const selected = isSelected(params, endpoint.endpointId);
      return <tr className={selected ? "selected-row" : undefined} key={endpoint.endpointId}><td><Link aria-current={selected ? "true" : undefined} className="table-primary" title={endpoint.hostname} to={{ pathname: `/endpoints/${endpoint.endpointId}`, search: selectedSearch(params, endpoint.endpointId) }}><strong>{endpoint.hostname}</strong><code>{endpoint.agentId}</code></Link></td><td>{endpoint.osType}<small>{endpoint.osVersion ?? t("endpoints.versionUnavailable")}</small></td><td><StatusPill value={endpoint.status} />{endpoint.isStale ? <span className="stale-inline">{t("endpoints.stale")}</span> : null}</td><td>{formatDateTime(endpoint.lastSeenAt)}</td><td><Link className="risk-cell" to={{ pathname: `/endpoints/${endpoint.endpointId}`, search: selectedSearch(params, endpoint.endpointId) }}><strong>{endpoint.risk.score}</strong><span className={`risk-level-text tone-${endpoint.risk.level.toLowerCase()}`}>{humanize(endpoint.risk.level)}</span></Link></td><td>{endpoint.risk.activeAlertCount}</td><td>{endpoint.risk.openIncidentCount}</td></tr>;
    })}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title={t("endpoints.noResults")} message={appliedFilters.length ? t("endpoints.noFilterMatch") : t("endpoints.noneRegistered")} />}</Panel> : null}
  </div>;
}
