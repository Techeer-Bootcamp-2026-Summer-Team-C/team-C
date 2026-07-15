import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, PageHeader, Pagination, Panel, Skeleton, StatusPill } from "../components/ui";
import type { EndpointListQuery } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime } from "../lib/format";
import { parseEndpointIds } from "../lib/endpointIds";
import { allowedValue } from "../lib/params";
import { numberParam, updateParams } from "../lib/url";

export function EndpointsPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const status = allowedValue(params.get("status"), ["ONLINE", "OFFLINE", "RETIRED"] as const);
  const osType = allowedValue(params.get("osType"), ["WINDOWS", "MACOS"] as const);
  const riskLevel = allowedValue(params.get("riskLevel"), ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const);
  const sortBy = allowedValue(params.get("sortBy"), ["riskScore", "lastSeenAt", "registeredAt"] as const) ?? "riskScore";
  const sortOrder = allowedValue(params.get("sortOrder"), ["asc", "desc"] as const) ?? "desc";
  const endpointIds = parseEndpointIds(params.get("endpointIds"));
  const query: EndpointListQuery = { page: numberParam(params, "page", 1), size: numberParam(params, "size", 50), sortBy, sortOrder };
  if (status) query.status = status;
  if (osType) query.osType = osType;
  if (riskLevel) query.riskLevel = riskLevel;
  if (endpointIds.length) query.endpointIds = endpointIds;
  const result = useQuery({ queryKey: ["endpoints", query], queryFn: ({ signal }) => api.endpoints(query, signal) });

  return <div className="page-stack">
    <PageHeader eyebrow={t("endpoints.eyebrow")} title={t("endpoints.title")} description={t("endpoints.description")} />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}>
      <Field label={t("filter.endpointIds")}><input onChange={(event) => setParams(updateParams(params, { endpointIds: event.target.value }))} placeholder="1, 2, 7" value={params.get("endpointIds") ?? ""} /></Field>
      <Field label={t("filter.status")}><select onChange={(event) => setParams(updateParams(params, { status: event.target.value }))} value={status ?? ""}><option value="">{t("filter.allStatuses")}</option><option>ONLINE</option><option>OFFLINE</option><option>RETIRED</option></select></Field>
      <Field label={t("endpoints.operatingSystem")}><select onChange={(event) => setParams(updateParams(params, { osType: event.target.value }))} value={osType ?? ""}><option value="">{t("endpoints.allSystems")}</option><option>WINDOWS</option><option>MACOS</option></select></Field>
      <Field label={t("endpoints.riskLevel")}><select onChange={(event) => setParams(updateParams(params, { riskLevel: event.target.value }))} value={riskLevel ?? ""}><option value="">{t("endpoints.allLevels")}</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></Field>
      <Field label={t("filter.sort")}><select onChange={(event) => setParams(updateParams(params, { sortBy: event.target.value }))} value={sortBy}><option value="riskScore">{t("endpoints.riskScore")}</option><option value="lastSeenAt">{t("endpoints.lastSeen")}</option><option value="registeredAt">{t("endpoints.registered")}</option></select></Field>
      <Field label={t("filter.order")}><select onChange={(event) => setParams(updateParams(params, { sortOrder: event.target.value }))} value={sortOrder}><option value="desc">{t("filter.descending")}</option><option value="asc">{t("filter.ascending")}</option></select></Field>
    </GlobalFilterBar>
    {result.isPending ? <Skeleton rows={8} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <Panel title={t("endpoints.inventory")} subtitle={t("endpoints.records", { total: result.data.data.total })}>
      {result.data.data.items.length ? <><DataTable label={t("endpoints.inventory")}><thead><tr><th scope="col">Endpoint</th><th scope="col">{t("endpoints.os")}</th><th scope="col">{t("filter.status")}</th><th scope="col">{t("endpoints.lastSeen")}</th><th scope="col" aria-sort={sortBy === "riskScore" ? (sortOrder === "desc" ? "descending" : "ascending") : "none"}>{t("endpoints.risk")}</th><th scope="col">{t("endpoints.activeAlerts")}</th><th scope="col">{t("endpoints.openIncidents")}</th></tr></thead><tbody>{result.data.data.items.map((endpoint) => <tr key={endpoint.endpointId}><td><Link className="table-primary" to={`/endpoints/${endpoint.endpointId}`}><strong>{endpoint.hostname}</strong><code>{endpoint.agentId}</code></Link></td><td>{endpoint.osType}<small>{endpoint.osVersion ?? t("endpoints.versionUnavailable")}</small></td><td><StatusPill value={endpoint.status} />{endpoint.isStale ? <span className="stale-inline">{t("endpoints.stale")}</span> : null}</td><td>{formatDateTime(endpoint.lastSeenAt)}</td><td><Link className="risk-cell" to={`/endpoints/${endpoint.endpointId}`}><strong>{endpoint.risk.score}</strong><StatusPill value={endpoint.risk.level} /></Link></td><td>{endpoint.risk.activeAlertCount}</td><td>{endpoint.risk.openIncidentCount}</td></tr>)}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title={t("endpoints.noResults")} message={params.size ? t("endpoints.noFilterMatch") : t("endpoints.noneRegistered")} />}
    </Panel> : null}
  </div>;
}
