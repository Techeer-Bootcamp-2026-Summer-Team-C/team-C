import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, PageHeader, Pagination, Panel, Skeleton, StatusPill } from "../components/ui";
import type { IncidentListQuery } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime } from "../lib/format";
import { allowedValue, positiveInteger } from "../lib/params";
import { numberParam, updateParams } from "../lib/url";

export function IncidentsPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const status = allowedValue(params.get("status"), ["OPEN", "CLOSED"] as const);
  const severity = allowedValue(params.get("severity"), ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const);
  const sortOrder = allowedValue(params.get("sortOrder"), ["asc", "desc"] as const) ?? "desc";
  const endpointId = positiveInteger(params.get("endpointId"));
  const query: IncidentListQuery = { ...time.query, page: numberParam(params, "page", 1), size: numberParam(params, "size", 50), sortOrder };
  if (status) query.status = status;
  if (severity) query.severity = severity;
  if (endpointId) query.endpointId = endpointId;
  const result = useQuery({ queryKey: ["incidents", query], queryFn: ({ signal }) => api.incidents(query, signal), enabled: time.valid });

  return <div className="page-stack">
    <PageHeader eyebrow={t("incident.eyebrow")} title={t("incident.title")} description={t("incident.description")} />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}>
      <TimeFilterFields params={params} setParams={setParams} />
      <Field label={t("filter.status")}><select onChange={(event) => setParams(updateParams(params, { status: event.target.value }))} value={status ?? ""}><option value="">{t("filter.allStatuses")}</option><option>OPEN</option><option>CLOSED</option></select></Field>
      <Field label={t("filter.severity")}><select onChange={(event) => setParams(updateParams(params, { severity: event.target.value }))} value={severity ?? ""}><option value="">{t("filter.allSeverities")}</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></Field>
      <Field label={t("filter.endpointId")}><input inputMode="numeric" onChange={(event) => setParams(updateParams(params, { endpointId: event.target.value }))} value={params.get("endpointId") ?? ""} /></Field>
      <Field label={t("filter.order")}><select onChange={(event) => setParams(updateParams(params, { sortOrder: event.target.value }))} value={sortOrder}><option value="desc">{t("filter.newestFirst")}</option><option value="asc">{t("filter.oldestFirst")}</option></select></Field>
    </GlobalFilterBar>
    {result.isPending && time.valid ? <Skeleton rows={7} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <Panel title={t("incident.queue")} subtitle={t("incident.records", { total: result.data.data.total })}>
      {result.data.data.items.length ? <><DataTable label={t("incident.queue")}><thead><tr><th scope="col">{t("incident.singular")}</th><th scope="col">Endpoint</th><th scope="col">{t("filter.severity")}</th><th scope="col">{t("filter.status")}</th><th scope="col">{t("incident.alerts")}</th><th scope="col">{t("incident.window")}</th><th scope="col" aria-sort={sortOrder === "desc" ? "descending" : "ascending"}>{t("incident.lastDetected")}</th></tr></thead><tbody>{result.data.data.items.map((incident) => <tr key={incident.incidentId}><td><Link className="table-primary" to={`/incidents/${incident.incidentId}`}><strong>{incident.title}</strong><code>{incident.correlationKey}</code></Link></td><td><Link to={`/endpoints/${incident.endpointId}`}>{incident.endpointId}</Link></td><td><StatusPill value={incident.severity} /></td><td><StatusPill value={incident.status} /></td><td>{incident.alertCount}</td><td>{formatDateTime(incident.windowStartAt)}<small>{t("common.to")} {formatDateTime(incident.windowEndAt)}</small></td><td>{formatDateTime(incident.lastDetectedAt)}</td></tr>)}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title={t("incident.noResults")} message={params.size ? t("incident.noFilterMatch") : t("incident.noneInRange")} />}
    </Panel> : null}
  </div>;
}
