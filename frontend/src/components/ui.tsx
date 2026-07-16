import { AlertTriangle, ArrowLeft, ArrowRight, CircleAlert, RefreshCw, SlidersHorizontal, X } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import type {
  AlertDetailDto,
  EdrStateDto,
  EndpointRiskDto,
  PagedData,
  ResponseGuidanceStepDto,
} from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import type { TranslationKey } from "../i18n/translations";
import { formatDateTime, humanize } from "../lib/format";
import { Badge, Button, Drawer, IconButton } from "./primitives";

export { Field } from "./primitives";

export function PageHeader({ eyebrow, title, description, actions }: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div><span>{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function Panel({ title, subtitle, meta, children, className = "" }: {
  title: string;
  subtitle?: string;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className={`panel ${className}`}>
      <header className="panel-heading">
        <div><h2 id={titleId}>{title}</h2>{subtitle ? <p>{subtitle}</p> : null}</div>
        {meta ? <div className="panel-meta">{meta}</div> : null}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function KpiCard({ label, value, detail, icon, to, tone = "neutral" }: {
  label: string;
  value: string | number;
  detail: string;
  icon: ReactNode;
  to?: string;
  tone?: string;
}) {
  const content = <><span className="kpi-icon">{icon}</span><span>{label}</span><strong>{value}</strong><small>{detail}</small>{to ? <ArrowRight aria-hidden="true" className="kpi-arrow" size={15} /> : null}</>;
  return to ? <Link className={`kpi-card ${tone}`} to={to}>{content}</Link> : <article className={`kpi-card ${tone}`}>{content}</article>;
}

export function StatusPill({ value }: { value: string }) {
  return <Badge className={`status-pill tone-${value.toLowerCase().replaceAll(" ", "-")}`}><i aria-hidden="true" />{humanize(value)}</Badge>;
}

export function EdrStateSummary({ state }: { state: EdrStateDto }) {
  const { t } = useI18n();
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className={`edr-state-summary tone-${state.status.toLowerCase()}`}>
      <header>
        <div><h2 className="eyebrow" id={titleId}>{t("edrState.current")}</h2><div className="edr-overall"><strong>{state.score}</strong><span>/ 100</span></div></div>
        <StatusPill value={state.status} />
      </header>
      <div aria-label={t("edrState.diagnostics")} className="edr-diagnostics">
        <EdrDiagnosticAxis label={t("edrState.threatLevel")} score={state.threatLevel.score} status={state.threatLevel.status} />
        <EdrDiagnosticAxis label={t("edrState.collectionHealth")} score={state.collectionHealth.score} status={state.collectionHealth.status} />
      </div>
      <div className="edr-reason-block">
        <h3>{t("edrState.reasonCodes")}</h3>
        {state.reasonCodes.length ? <ul>{state.reasonCodes.map((reason) => <li key={reason}>{humanize(reason)}</li>)}</ul> : <p>{t("edrState.noReasons")}</p>}
      </div>
      <footer>{t("edrState.calculated", { time: formatDateTime(state.calculatedAt) })}</footer>
    </section>
  );
}

function EdrDiagnosticAxis({ label, score, status }: { label: string; score: number; status: string }) {
  return <div className={`edr-axis tone-${status.toLowerCase()}`}>
    <div><span>{label}</span><strong>{score}</strong><small>{humanize(status)}</small></div>
    <div aria-label={`${label}: ${score} / 100, ${humanize(status)}`} aria-valuemax={100} aria-valuemin={0} aria-valuenow={score} className="edr-axis-track" role="progressbar"><i style={{ width: `${score}%` }} /></div>
  </div>;
}

export function GlobalFilterBar({ children, onClear, hasFilters }: {
  children: ReactNode;
  onClear: () => void;
  hasFilters: boolean;
}) {
  return <FilterBar hasFilters={hasFilters} onClear={onClear} primary={children} />;
}

export interface AppliedFilter {
  key: string;
  label: string;
  value: string;
}

export function FilterBar({ primary, advanced, appliedFilters = [], onRemoveFilter, onClear, hasFilters }: {
  primary: ReactNode;
  advanced?: ReactNode;
  appliedFilters?: readonly AppliedFilter[];
  onRemoveFilter?: (key: string) => void;
  onClear: () => void;
  hasFilters: boolean;
}) {
  const { t } = useI18n();
  const [advancedOpen, setAdvancedOpen] = useState(false);
  return <section aria-label={t("filter.filters")} className="filter-bar">
    <div className="filter-bar-main">
      <div className="filter-fields">{primary}</div>
      <div className="filter-actions">
        {advanced ? <Button aria-expanded={advancedOpen} onClick={() => setAdvancedOpen(true)} type="button" variant="ghost"><SlidersHorizontal aria-hidden="true" size={16} />{t("filter.more")}</Button> : null}
        <Button disabled={!hasFilters} onClick={onClear} type="button" variant="ghost">{t("filter.clear")}</Button>
      </div>
    </div>
    {appliedFilters.length ? <ul aria-label={t("filter.active")} className="applied-filter-list">
      {appliedFilters.map((filter) => <li key={filter.key}><span>{filter.label}</span><strong>{filter.value}</strong>{onRemoveFilter ? <IconButton aria-label={t("filter.remove", { label: filter.label })} onClick={() => onRemoveFilter(filter.key)} type="button"><X aria-hidden="true" size={13} /></IconButton> : null}</li>)}
    </ul> : null}
    {advanced ? <Drawer closeLabel={t("filter.closeMore")} label={t("filter.moreTitle")} onClose={() => setAdvancedOpen(false)} open={advancedOpen} side="right" title={t("filter.moreTitle")}>
      <div className="filter-drawer-fields">{advanced}</div>
      <div className="filter-drawer-actions"><Button onClick={() => setAdvancedOpen(false)} type="button" variant="primary">{t("filter.done")}</Button></div>
    </Drawer> : null}
  </section>;
}

export function DataTable({ label, caption = label, children, busy = false }: { label: string; caption?: string; children: ReactNode; busy?: boolean }) {
  return <div aria-busy={busy || undefined} aria-label={`${label} table`} className="table-scroll" role="region" tabIndex={0}><table><caption className="sr-only">{caption}</caption>{children}</table></div>;
}

export function SortableHeader({ label, active, direction, onSort }: {
  label: string;
  active: boolean;
  direction: "asc" | "desc";
  onSort: () => void;
}) {
  const { t } = useI18n();
  const state = active ? (direction === "desc" ? "descending" : "ascending") : "none";
  const next = active && direction === "desc" ? t("filter.ascending") : t("filter.descending");
  return <th aria-sort={state} scope="col"><button aria-label={t("filter.sortColumn", { label, direction: next })} className="sort-header" onClick={onSort} type="button"><span>{label}</span><span aria-hidden="true">{active ? (direction === "desc" ? "↓" : "↑") : "↕"}</span></button></th>;
}

export function Pagination<T>({ page }: { page: PagedData<T> }) {
  const { t } = useI18n();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const totalPages = Math.max(1, Math.ceil(page.total / page.size));
  const pageUrl = (targetPage: number): string => {
    const next = new URLSearchParams(params);
    if (targetPage <= 1) next.delete("page"); else next.set("page", String(targetPage));
    return `${location.pathname}${next.size ? `?${next}` : ""}`;
  };
  return (
    <nav className="pagination" aria-label={t("pagination.label")}>
      {page.page <= 1 ? <span aria-disabled="true" className="disabled"><ArrowLeft aria-hidden="true" size={15} />{t("pagination.previous")}</span> : <Link to={pageUrl(page.page - 1)}><ArrowLeft aria-hidden="true" size={15} />{t("pagination.previous")}</Link>}
      <span>{t("pagination.summary", { page: page.page, totalPages, total: page.total })}</span>
      <label className="page-size"><span>{t("pagination.pageSize")}</span><select aria-label={t("pagination.pageSize")} onChange={(event) => setParams(updateListParams(params, { size: event.target.value }))} value={String(page.size)}>{![25, 50, 100].includes(page.size) ? <option value={page.size}>{page.size}</option> : null}<option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label>
      {page.page >= totalPages ? <span aria-disabled="true" className="disabled">{t("pagination.next")}<ArrowRight aria-hidden="true" size={15} /></span> : <Link to={pageUrl(page.page + 1)}>{t("pagination.next")}<ArrowRight aria-hidden="true" size={15} /></Link>}
    </nav>
  );
}

function updateListParams(current: URLSearchParams, values: Record<string, string | null>): URLSearchParams {
  const next = new URLSearchParams(current);
  for (const [key, value] of Object.entries(values)) {
    if (!value) next.delete(key); else next.set(key, value);
  }
  next.delete("page");
  return next;
}

export function Skeleton({ rows = 5 }: { rows?: number }) {
  const { t } = useI18n();
  return <div aria-label={t("common.loading")} className="skeleton" role="status"><span className="skeleton-heading" />{Array.from({ length: rows }, (_, index) => <span className="skeleton-row" key={index} />)}</div>;
}

export function EmptyState({ title, message }: { title: string; message: string }) {
  return <div className="state-card empty"><CircleAlert aria-hidden="true" size={22} /><strong>{title}</strong><p>{message}</p></div>;
}

export function ErrorState({ error, onRetry, archiveAction = false }: {
  error: unknown;
  onRetry?: () => void;
  archiveAction?: boolean;
}) {
  const { locale, t } = useI18n();
  const apiError = error instanceof ApiError ? error : null;
  const translatedErrorKey = apiError ? API_ERROR_KEYS[apiError.code] : undefined;
  const stateClass = apiError?.code === "FORBIDDEN" ? "forbidden" : apiError?.code === "ARCHIVE_NOT_READY" ? "archive-not-ready" : "error";
  const errorMessage = apiError
    ? locale === "KO" && translatedErrorKey ? t(translatedErrorKey) : apiError.message
    : t("error.dataLoad");
  return (
    <div className={`state-card ${stateClass}`} role="alert">
      <AlertTriangle aria-hidden="true" size={22} />
      <strong>{errorMessage}</strong>
      <p>{apiError?.retryable ? t("error.retryableHelp") : t("error.actionHelp")}</p>
      {apiError?.requestId ? <code>{t("common.requestId", { requestId: apiError.requestId })}</code> : <span>{t("common.requestIdUnavailable")}</span>}
      {apiError?.details.length ? <ul>{apiError.details.map((detail, index) => <li key={`${detail.field ?? "state"}-${index}`}>{detail.message}{detail.context ? ` · ${JSON.stringify(detail.context)}` : ""}</li>)}</ul> : null}
      <div className="state-actions">{onRetry ? <button className="button" onClick={onRetry} type="button"><RefreshCw aria-hidden="true" size={15} />{t("common.retry")}</button> : null}{archiveAction || apiError?.code === "ARCHIVE_NOT_READY" ? <Link className="button" to="/operations/archives">{t("error.archiveAction")}</Link> : null}</div>
    </div>
  );
}

export function InvalidFilterState({ message }: { message?: string }) {
  const { t } = useI18n();
  return <div className="state-card invalid" role="alert"><CircleAlert aria-hidden="true" size={22} /><strong>{t("filter.invalidTitle")}</strong><p>{message ?? t("filter.invalidDescription")}</p></div>;
}

export function RefetchingIndicator() {
  const { t } = useI18n();
  return <div aria-live="polite" className="refetching-indicator" role="status"><RefreshCw aria-hidden="true" size={14} /><span>{t("common.refreshing")}</span></div>;
}

export function PartialFailureWarning({ message }: { message: string }) {
  const { t } = useI18n();
  return <div className="partial-warning" role="status"><AlertTriangle aria-hidden="true" size={17} /><div><strong>{t("error.partialTitle")}</strong><span>{message}</span></div></div>;
}

export function QueryFeedback({ invalid = false, invalidMessage, pending, fetching, refetchError = false, error, hasData, onRetry, rows = 8 }: {
  invalid?: boolean;
  invalidMessage?: string;
  pending: boolean;
  fetching: boolean;
  refetchError?: boolean;
  error: unknown;
  hasData: boolean;
  onRetry: () => void;
  rows?: number;
}) {
  if (invalid) return <InvalidFilterState {...(invalidMessage ? { message: invalidMessage } : {})} />;
  return <>
    {pending ? <Skeleton rows={rows} /> : null}
    {error && !hasData ? <ErrorState error={error} onRetry={onRetry} /> : null}
    {refetchError && hasData ? <StaleWarning error={error} onRetry={onRetry} /> : null}
    {fetching && hasData && !refetchError ? <RefetchingIndicator /> : null}
  </>;
}

export function StaleWarning({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const { t } = useI18n();
  const requestId = error instanceof ApiError ? error.requestId : null;
  return <div className="stale-warning" role="alert"><AlertTriangle aria-hidden="true" size={17} /><span>{t("error.refreshStale")}{requestId ? ` ${t("common.requestId", { requestId })}.` : ""}</span><button onClick={onRetry} type="button">{t("common.retry")}</button></div>;
}

export function DefinitionGrid({ items }: { items: readonly { label: string; value: ReactNode }[] }) {
  return <dl className="definition-grid">{items.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>;
}

export function ResponseGuidance({ steps }: { steps: ResponseGuidanceStepDto[] }) {
  const { t } = useI18n();
  if (!steps.length) return <EmptyState title={t("empty.noResponseGuidance")} message={t("empty.responseGuidanceDescription")} />;
  return <ol aria-label={t("alert.guidanceSteps")} className="guidance-list">{steps.map((step) => <li key={step.order}><span>{step.order}</span><div><div className="guidance-title"><strong>{step.title}</strong>{step.requiresManualAction ? <Badge tone="warning">{t("alert.manualAction")}</Badge> : null}</div><p>{step.description}</p></div></li>)}</ol>;
}

export function RiskFactorList({ risk }: { risk: EndpointRiskDto }) {
  const { locale, t } = useI18n();
  if (!risk.riskFactors.length) return <EmptyState title={t("empty.noRiskFactors")} message={t("empty.riskFactorsDescription")} />;
  return <ul className="risk-factor-list">{risk.riskFactors.map((factor) => <li key={`${factor.sourceType}-${factor.sourceId}-${factor.code}`}><span className="factor-score">+{factor.contribution}</span><div><strong>{factor.title}</strong><p>{factor.description}</p><Link to={factor.sourceType === "ALERT" ? `/alerts/${factor.sourceId}` : `/incidents/${factor.sourceId}`}>{t("risk.openSource", { sourceType: locale === "KO" ? (factor.sourceType === "ALERT" ? "Alert" : "Incident") : factor.sourceType.toLowerCase() })}</Link></div></li>)}</ul>;
}

export function SourceEvent({ alert }: { alert: AlertDetailDto }) {
  const { t } = useI18n();
  if (!alert.sourceEvent) return <EmptyState title={t("empty.sourceEventUnavailable")} message={t("empty.sourceEventDescription")} />;
  const event = alert.sourceEvent;
  return <Link className="source-event" to={`/events/${event.eventId}?endpointId=${event.endpointId}&occurredAt=${encodeURIComponent(event.occurredAt)}`}><span>{event.eventType}</span><strong>{event.processName ?? event.remoteDomain ?? event.filePath ?? event.eventId}</strong><small>{formatDateTime(event.occurredAt)}</small></Link>;
}

export function Inspector({ title, description, children, actions }: { title: string; description?: string; children: ReactNode; actions?: ReactNode }) {
  const titleId = useId();
  return <aside aria-labelledby={titleId} className="inspector"><header><div><span className="eyebrow">INSPECTOR</span><h2 id={titleId}>{title}</h2>{description ? <p>{description}</p> : null}</div>{actions ? <div className="inspector-actions">{actions}</div> : null}</header><div className="inspector-body">{children}</div></aside>;
}

export function MasterDetail({ list, detail, label }: { list: ReactNode; detail: ReactNode; label?: string }) {
  return <section {...(label ? { "aria-label": label } : {})} className="master-detail"><div className="master-list">{list}</div><div className="master-inspector">{detail}</div></section>;
}

export function ChartFrame({ title, description, meta, children, fallback }: { title: string; description: string; meta?: ReactNode; children: ReactNode; fallback: ReactNode }) {
  const titleId = useId();
  return <section aria-labelledby={titleId} className="chart-frame"><header><div><h2 id={titleId}>{title}</h2><p>{description}</p></div>{meta ? <div className="chart-frame-meta">{meta}</div> : null}</header><div className="chart-frame-visual">{children}</div><details className="chart-frame-fallback"><summary>{useChartDataLabel()}</summary>{fallback}</details></section>;
}

function useChartDataLabel(): string {
  return useI18n().t("charts.viewData", { label: "data" });
}

const API_ERROR_KEYS: Readonly<Record<string, TranslationKey>> = {
  VALIDATION_ERROR: "error.validation",
  INVALID_TOKEN: "error.invalidToken",
  FORBIDDEN: "error.forbidden",
  NOT_FOUND: "error.notFound",
  SERVICE_UNAVAILABLE: "error.serviceUnavailable",
  ARCHIVE_NOT_READY: "error.archiveNotReady",
  NETWORK_ERROR: "error.network",
  INVALID_ENVELOPE: "error.invalidEnvelope",
};
