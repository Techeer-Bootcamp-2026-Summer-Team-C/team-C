import { AlertTriangle, ArrowLeft, ArrowRight, CircleAlert, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import type {
  AlertDetailDto,
  EndpointRiskDto,
  PagedData,
  ResponseGuidanceStepDto,
} from "../contracts";
import { useI18n } from "../i18n/LocaleContext";
import type { TranslationKey } from "../i18n/translations";
import { formatDateTime, humanize } from "../lib/format";

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
  return (
    <section className={`panel ${className}`}>
      <header className="panel-heading">
        <div><h2>{title}</h2>{subtitle ? <p>{subtitle}</p> : null}</div>
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
  return <span className={`status-pill tone-${value.toLowerCase().replaceAll(" ", "-")}`}><i aria-hidden="true" />{humanize(value)}</span>;
}

export function EdrStatePill({ state, score, reasons, calculatedAt }: {
  state: string;
  score: number;
  reasons: readonly string[];
  calculatedAt: string;
}) {
  const { t } = useI18n();
  return (
    <section className={`edr-state tone-${state.toLowerCase()}`} aria-label={t("edrState.aria", { state, score })}>
      <div><span>{t("edrState.current")}</span><strong>{state}</strong></div>
      <div className="edr-score"><strong>{score}</strong><span>/ 100</span></div>
      <div className="edr-reasons">
        <span>{reasons.length ? reasons.map(humanize).join(" · ") : t("edrState.noReasons")}</span>
        <small>{t("edrState.calculated", { time: formatDateTime(calculatedAt) })}</small>
      </div>
    </section>
  );
}

export function GlobalFilterBar({ children, onClear, hasFilters }: {
  children: ReactNode;
  onClear: () => void;
  hasFilters: boolean;
}) {
  const { t } = useI18n();
  return <section className="filter-bar" aria-label={t("filter.filters")}><div className="filter-fields">{children}</div><button className="button ghost" disabled={!hasFilters} onClick={onClear} type="button">{t("filter.clear")}</button></section>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

export function DataTable({ label, children }: { label: string; children: ReactNode }) {
  return <div className="table-scroll" role="region" aria-label={label} tabIndex={0}><table>{children}</table></div>;
}

export function Pagination<T>({ page }: { page: PagedData<T> }) {
  const { t } = useI18n();
  const totalPages = Math.max(1, Math.ceil(page.total / page.size));
  return (
    <nav className="pagination" aria-label={t("pagination.label")}>
      <Link aria-disabled={page.page <= 1} className={page.page <= 1 ? "disabled" : ""} to={pageUrl(page.page - 1)}><ArrowLeft aria-hidden="true" size={15} />{t("pagination.previous")}</Link>
      <span>{t("pagination.summary", { page: page.page, totalPages, total: page.total })}</span>
      <Link aria-disabled={page.page >= totalPages} className={page.page >= totalPages ? "disabled" : ""} to={pageUrl(page.page + 1)}>{t("pagination.next")}<ArrowRight aria-hidden="true" size={15} /></Link>
    </nav>
  );
}

function pageUrl(page: number): string {
  const params = new URLSearchParams(window.location.search);
  if (page <= 1) params.delete("page"); else params.set("page", String(page));
  return `${window.location.pathname}${params.size ? `?${params}` : ""}`;
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
  const errorMessage = apiError
    ? locale === "KO" && translatedErrorKey ? t(translatedErrorKey) : apiError.message
    : t("error.dataLoad");
  return (
    <div className="state-card error" role="alert">
      <AlertTriangle aria-hidden="true" size={22} />
      <strong>{errorMessage}</strong>
      <p>{apiError?.retryable ? t("error.retryableHelp") : t("error.actionHelp")}</p>
      {apiError?.requestId ? <code>{t("common.requestId", { requestId: apiError.requestId })}</code> : <span>{t("common.requestIdUnavailable")}</span>}
      {apiError?.details.length ? <ul>{apiError.details.map((detail, index) => <li key={`${detail.field ?? "state"}-${index}`}>{detail.message}{detail.context ? ` · ${JSON.stringify(detail.context)}` : ""}</li>)}</ul> : null}
      <div className="state-actions">{onRetry ? <button className="button" onClick={onRetry} type="button"><RefreshCw aria-hidden="true" size={15} />{t("common.retry")}</button> : null}{archiveAction ? <Link className="button" to="/operations/archives">{t("error.archiveAction")}</Link> : null}</div>
    </div>
  );
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
  return <ol className="guidance-list">{steps.map((step) => <li key={step.order}><span>{step.order}</span><div><div className="guidance-title"><strong>{step.title}</strong>{step.requiresManualAction ? <StatusPill value="MANUAL ACTION" /> : null}</div><p>{step.description}</p></div></li>)}</ol>;
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

export function MasterDetail({ list, detail }: { list: ReactNode; detail: ReactNode }) {
  return <div className="master-detail"><div>{list}</div><aside>{detail}</aside></div>;
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
