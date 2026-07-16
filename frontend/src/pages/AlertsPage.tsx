import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { Badge } from "../components/primitives";
import { readTimeFilter, TimeFilterFields } from "../components/filters";
import { DataTable, EmptyState, Field, FilterBar, PageHeader, Pagination, Panel, QueryFeedback, SortableHeader, StatusPill } from "../components/ui";
import type { AlertListQuery } from "../contracts";
import { appliedFilterDescriptors, hasInvalidEnum, hasInvalidPagination, hasInvalidPositiveInteger, isSelected, removeListFilter, selectedSearch } from "../features/listInteractions";
import { useI18n } from "../i18n/LocaleContext";
import { formatDateTime, humanize } from "../lib/format";
import { allowedValue, positiveInteger } from "../lib/params";
import { numberParam, stringParam, updateParams } from "../lib/url";

const STATUSES = ["OPEN", "IN_PROGRESS", "RESOLVED"] as const;
const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
const SORT_FIELDS = ["priority", "detectedAt", "severity", "riskScore", "status"] as const;

export function AlertsPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const time = readTimeFilter(params);
  const status = allowedValue(params.get("status"), STATUSES);
  const severity = allowedValue(params.get("severity"), SEVERITIES);
  const sortBy = allowedValue(params.get("sortBy"), SORT_FIELDS) ?? "priority";
  const sortOrder = allowedValue(params.get("sortOrder"), ["asc", "desc"] as const) ?? "desc";
  const endpointId = positiveInteger(params.get("endpointId"));
  const ruleCode = stringParam(params, "ruleCode").trim();
  const invalid = !time.valid
    || hasInvalidEnum(params, "status", STATUSES)
    || hasInvalidEnum(params, "severity", SEVERITIES)
    || hasInvalidEnum(params, "sortBy", SORT_FIELDS)
    || hasInvalidEnum(params, "sortOrder", ["asc", "desc"])
    || hasInvalidPositiveInteger(params, "endpointId")
    || hasInvalidPagination(params);
  const query: AlertListQuery = { ...time.query, page: numberParam(params, "page", 1), size: numberParam(params, "size", 50), sortBy, sortOrder };
  if (status) query.status = status;
  if (severity) query.severity = severity;
  if (endpointId) query.endpointId = endpointId;
  if (ruleCode) query.ruleCode = ruleCode;
  const result = useQuery({ queryKey: ["alerts", query], queryFn: ({ signal }) => api.alerts(query, signal), enabled: !invalid });
  const appliedFilters = appliedFilterDescriptors(params, [
    { key: "timePreset", label: t("filter.timeRange"), format: humanize },
    { key: "from", label: t("filter.from") },
    { key: "to", label: t("filter.to") },
    { key: "status", label: t("filter.status"), format: humanize },
    { key: "severity", label: t("filter.severity"), format: humanize },
    { key: "endpointId", label: t("filter.endpointId") },
    { key: "ruleCode", label: t("alerts.ruleCode") },
    { key: "sortBy", label: t("filter.sort"), format: humanize },
    { key: "sortOrder", label: t("filter.order"), format: humanize },
  ]);
  const updateSort = (nextSortBy: typeof SORT_FIELDS[number]) => {
    const nextOrder = sortBy === nextSortBy && sortOrder === "desc" ? "asc" : "desc";
    setParams(updateParams(params, { sortBy: nextSortBy, sortOrder: nextOrder }));
  };

  return <div className="page-stack">
    <PageHeader eyebrow={t("alerts.eyebrow")} title={t("alerts.title")} description={t("alerts.description")} />
    <FilterBar
      advanced={<>
        <Field label={t("filter.endpointId")}><input inputMode="numeric" onChange={(event) => setParams(updateParams(params, { endpointId: event.target.value }))} value={params.get("endpointId") ?? ""} /></Field>
        <Field label={t("alerts.ruleCode")}><input onChange={(event) => setParams(updateParams(params, { ruleCode: event.target.value }))} value={ruleCode} /></Field>
        <Field label={t("filter.sort")}><select onChange={(event) => setParams(updateParams(params, { sortBy: event.target.value }))} value={sortBy}><option value="priority">{t("filter.priority")}</option><option value="detectedAt">{t("alerts.detected")}</option><option value="severity">{t("filter.severity")}</option><option value="riskScore">{t("alerts.risk")}</option><option value="status">{t("filter.status")}</option></select></Field>
        <Field {...(sortBy === "priority" ? { helper: t("alerts.priorityOrder") } : {})} label={t("filter.order")}><select disabled={sortBy === "priority"} onChange={(event) => setParams(updateParams(params, { sortOrder: event.target.value }))} value={sortOrder}><option value="desc">{t("filter.descending")}</option><option value="asc">{t("filter.ascending")}</option></select></Field>
      </>}
      appliedFilters={appliedFilters}
      hasFilters={appliedFilters.length > 0}
      onClear={() => setParams({})}
      onRemoveFilter={(key) => setParams(removeListFilter(params, key))}
      primary={<>
        <TimeFilterFields params={params} setParams={setParams} />
        <Field label={t("filter.status")}><select onChange={(event) => setParams(updateParams(params, { status: event.target.value }))} value={status ?? ""}><option value="">{t("filter.allStatuses")}</option>{STATUSES.map((value) => <option key={value}>{value}</option>)}</select></Field>
        <Field label={t("filter.severity")}><select onChange={(event) => setParams(updateParams(params, { severity: event.target.value }))} value={severity ?? ""}><option value="">{t("filter.allSeverities")}</option>{SEVERITIES.map((value) => <option key={value}>{value}</option>)}</select></Field>
      </>}
    />
    <QueryFeedback error={result.error} fetching={result.isFetching} hasData={Boolean(result.data)} invalid={invalid} onRetry={() => void result.refetch()} pending={result.isPending && !invalid} refetchError={result.isRefetchError} rows={8} />
    {!invalid && result.data ? <Panel meta={sortBy === "priority" ? <Badge tone="info">{t("filter.priority")}</Badge> : null} title={t("alerts.queue")} subtitle={sortBy === "priority" ? `${t("alerts.records", { total: result.data.data.total })} · ${t("alerts.priorityOrder")}` : t("alerts.records", { total: result.data.data.total })}>
      {result.data.data.items.length ? <><DataTable busy={result.isFetching} label={t("alerts.queue")}><thead><tr><th scope="col">{t("alerts.rule")}</th><SortableHeader active={sortBy === "severity"} direction={sortOrder} label={t("filter.severity")} onSort={() => updateSort("severity")} /><SortableHeader active={sortBy === "riskScore"} direction={sortOrder} label={t("alerts.risk")} onSort={() => updateSort("riskScore")} /><SortableHeader active={sortBy === "status"} direction={sortOrder} label={t("filter.status")} onSort={() => updateSort("status")} /><th scope="col">{t("alerts.agent")}</th><SortableHeader active={sortBy === "detectedAt"} direction={sortOrder} label={t("alerts.detected")} onSort={() => updateSort("detectedAt")} /></tr></thead><tbody>{result.data.data.items.map((alert) => {
        const selected = isSelected(params, alert.alertId);
        return <tr className={selected ? "selected-row" : undefined} key={alert.alertId}><td><Link aria-current={selected ? "true" : undefined} className="table-primary" to={{ pathname: `/alerts/${alert.alertId}`, search: selectedSearch(params, alert.alertId) }}><strong>{alert.ruleName}</strong><code>{alert.ruleCode} · v{alert.ruleVersion}</code></Link></td><td><StatusPill value={alert.severity} /></td><td>{alert.riskScore}</td><td><StatusPill value={alert.status} /></td><td><code>{alert.agentId}</code></td><td>{formatDateTime(alert.detectedAt)}</td></tr>;
      })}</tbody></DataTable><Pagination page={result.data.data} /></> : <EmptyState title={t("alerts.noResults")} message={appliedFilters.length ? t("alerts.noFilterMatch") : t("alerts.noneInRange")} />}
    </Panel> : null}
  </div>;
}
