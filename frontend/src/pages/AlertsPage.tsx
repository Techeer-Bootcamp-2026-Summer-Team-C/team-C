import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { DataTable, EmptyState, ErrorState, Field, GlobalFilterBar, PageHeader, Pagination, Panel, Skeleton, StatusPill } from "../components/ui";
import type { AlertListQuery } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime } from "../lib/format";
import { allowedValue, positiveInteger } from "../lib/params";
import { numberParam, stringParam, updateParams } from "../lib/url";

export function AlertsPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const status = allowedValue(params.get("status"), ["OPEN", "IN_PROGRESS", "RESOLVED"] as const);
  const severity = allowedValue(params.get("severity"), ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const);
  const sortOrder = allowedValue(params.get("sortOrder"), ["asc", "desc"] as const) ?? "desc";
  const endpointId = positiveInteger(params.get("endpointId"));
  const ruleCode = stringParam(params, "ruleCode").trim();
  const query: AlertListQuery = { ...time.query, page: numberParam(params, "page", 1), size: numberParam(params, "size", 50), sortOrder };
  if (status) query.status = status;
  if (severity) query.severity = severity;
  if (endpointId) query.endpointId = endpointId;
  if (ruleCode) query.ruleCode = ruleCode;
  const result = useQuery({ queryKey: ["alerts", query], queryFn: ({ signal }) => api.alerts(query, signal), enabled: time.valid });

  return <div className="page-stack">
    <PageHeader eyebrow={t("alerts.eyebrow")} title={t("alerts.title")} description={t("alerts.description")} />
    <GlobalFilterBar hasFilters={params.size > 0} onClear={() => setParams({})}>
      <TimeFilterFields params={params} setParams={setParams} />
      <Field label={t("filter.status")}><select onChange={(event) => setParams(updateParams(params, { status: event.target.value }))} value={status ?? ""}><option value="">{t("filter.allStatuses")}</option><option>OPEN</option><option>IN_PROGRESS</option><option>RESOLVED</option></select></Field>
      <Field label={t("filter.severity")}><select onChange={(event) => setParams(updateParams(params, { severity: event.target.value }))} value={severity ?? ""}><option value="">{t("filter.allSeverities")}</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></Field>
      <Field label={t("filter.endpointId")}><input inputMode="numeric" onChange={(event) => setParams(updateParams(params, { endpointId: event.target.value }))} value={params.get("endpointId") ?? ""} /></Field>
      <Field label={t("alerts.ruleCode")}><input onChange={(event) => setParams(updateParams(params, { ruleCode: event.target.value }))} value={ruleCode} /></Field>
      <Field label={t("filter.order")}><select onChange={(event) => setParams(updateParams(params, { sortOrder: event.target.value }))} value={sortOrder}><option value="desc">{t("filter.newestFirst")}</option><option value="asc">{t("filter.oldestFirst")}</option></select></Field>
    </GlobalFilterBar>
    {result.isPending && time.valid ? <Skeleton rows={8} /> : null}
    {result.error ? <ErrorState error={result.error} onRetry={() => void result.refetch()} /> : null}
    {result.data ? <Panel title={t("alerts.queue")} subtitle={t("alerts.records", { total: result.data.data.total })}>
      {result.data.data.items.length ? <><DataTable label={t("alerts.queue")}><thead><tr><th scope="col">{t("alerts.rule")}</th><th scope="col">{t("filter.severity")}</th><th scope="col">{t("alerts.risk")}</th><th scope="col">{t("filter.status")}</th><th scope="col">{t("alerts.agent")}</th><th scope="col" aria-sort={sortOrder === "desc" ? "descending" : "ascending"}>{t("alerts.detected")}</th></tr></thead><tbody>{result.data.data.items.map((alert) => <tr key={alert.alertId}><td><Link className="table-primary" to={{ pathname: `/alerts/${alert.alertId}`, search: params.size ? `?${params.toString()}` : "" }}><strong>{alert.ruleName}</strong><code>{alert.ruleCode} · v{alert.ruleVersion}</code></Link></td><td><StatusPill value={alert.severity} /></td><td>{alert.riskScore}</td><td><StatusPill value={alert.status} /></td><td><code>{alert.agentId}</code></td><td>{formatDateTime(alert.detectedAt)}</td></tr>)}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title={t("alerts.noResults")} message={params.size ? t("alerts.noFilterMatch") : t("alerts.noneInRange")} />}
    </Panel> : null}
  </div>;
}
