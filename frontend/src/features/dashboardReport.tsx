import type { CSSProperties, ReactNode } from "react";
import type { Locale } from "../i18n/types";

export type DashboardReportScope = "selected-period" | "current-snapshot" | "current-view";

export interface DashboardReportMetric {
  label: string;
  value: string;
  detail?: string;
  scope: DashboardReportScope;
}

interface DashboardReportSignal {
  label: string;
  value: string;
  status?: string;
  details: string[];
  scope: DashboardReportScope;
}

interface DashboardReportBreakdownRow {
  label: string;
  value: string;
  count: number;
  detail?: string;
  tone: string;
}

interface DashboardReportBreakdown {
  title: string;
  rows: DashboardReportBreakdownRow[];
  scope: DashboardReportScope;
}

interface DashboardReportTrendSeries {
  label: string;
  values: Array<number | null>;
  tone: string;
}

interface DashboardReportTrend {
  title: string;
  categories: string[];
  series: DashboardReportTrendSeries[];
  scope: DashboardReportScope;
}

interface DashboardReportTable {
  title: string;
  columns: string[];
  rows: string[][];
  scope: DashboardReportScope;
}

interface DashboardReportFactGroup {
  title: string;
  items: Array<{ label: string; value: string }>;
  scope: DashboardReportScope;
}

interface DashboardReportRecordGroup {
  title: string;
  records: Array<{ label: string; details: string[] }>;
  scope: DashboardReportScope;
}

export interface DashboardReportContext {
  generatedAt: Date;
  operator: string;
  pageTitle: string;
  pathname: string;
  search: string;
  userRole: string;
}

export interface DashboardReportSnapshot extends DashboardReportContext {
  breakdowns: DashboardReportBreakdown[];
  factGroups: DashboardReportFactGroup[];
  metrics: DashboardReportMetric[];
  pageLimited: boolean;
  recordGroups: DashboardReportRecordGroup[];
  signals: DashboardReportSignal[];
  tables: DashboardReportTable[];
  trends: DashboardReportTrend[];
  visibleRowCount: number;
}

interface ReportFilter {
  label: string;
  value: string;
}

interface ReportPage {
  content: ReactNode;
  key: string;
  scope?: DashboardReportScope;
  title: string;
}

const CURRENT_SNAPSHOT_BLOCKS = new Set(["edr-state", "kpi-high-risk-endpoints", "fleet-distribution", "highest-risk-endpoints"]);
const SELECTED_PERIOD_BLOCKS = new Set(["kpi-alerts", "kpi-critical-alerts", "kpi-open-incidents", "detection-activity", "alert-severity", "incident-queue"]);
const TIME_QUERY_KEYS = ["timePreset", "from", "to"];

const REPORT_COPY = {
  EN: {
    appliedScope: "Applied filters",
    currentSnapshot: "Current snapshot",
    currentView: "Current view",
    documentType: "EDR OPERATIONS REPORT",
    empty: "No structured evidence is rendered on this page.",
    executiveSummary: "Executive Summary",
    generated: "Generated",
    operator: "Operator",
    page: "Page",
    pageSize: "Page size",
    reportId: "Report ID",
    selectedPeriod: "Selected period",
    userRole: "Access role",
    visibleBoundary: (rows: number) => `Visible page · ${rows} rows`,
  },
  KO: {
    appliedScope: "적용 필터",
    currentSnapshot: "현재 스냅샷",
    currentView: "현재 화면",
    documentType: "EDR 운영 리포트",
    empty: "현재 화면에 구조화된 결과가 없습니다.",
    executiveSummary: "Executive Summary",
    generated: "생성 시각",
    operator: "Operator",
    page: "페이지",
    pageSize: "페이지 크기",
    reportId: "Report ID",
    selectedPeriod: "선택 기간",
    userRole: "Access role",
    visibleBoundary: (rows: number) => `현재 페이지 · ${rows}행`,
  },
} as const;

const FILTER_LABELS: Record<Locale, Record<string, string>> = {
  EN: {
    timePreset: "Time range", from: "From (UTC)", to: "To (UTC)", endpointId: "Endpoint ID", endpointIds: "Endpoint IDs",
    severity: "Severity", status: "Status", riskLevel: "Risk level", osType: "Operating system", sortBy: "Sort by",
    sortOrder: "Sort order", q: "Search", processName: "Process name", eventType: "Event type", ruleCode: "Rule code", domain: "Domain",
  },
  KO: {
    timePreset: "조회 기간", from: "시작 (UTC)", to: "종료 (UTC)", endpointId: "Endpoint ID", endpointIds: "Endpoint ID 목록",
    severity: "심각도", status: "상태", riskLevel: "Risk 등급", osType: "운영체제", sortBy: "정렬 기준",
    sortOrder: "정렬 순서", q: "검색어", processName: "Process 이름", eventType: "Event 유형", ruleCode: "Rule 코드", domain: "Domain",
  },
};

export function collectDashboardReport(
  root: HTMLElement | null,
  contextOrGeneratedAt: Partial<DashboardReportContext> | Date = {},
): DashboardReportSnapshot {
  const context = contextOrGeneratedAt instanceof Date ? { generatedAt: contextOrGeneratedAt } : contextOrGeneratedAt;
  const reportContext: DashboardReportContext = {
    generatedAt: context.generatedAt ?? new Date(),
    operator: context.operator ?? "—",
    pageTitle: context.pageTitle ?? "Report",
    pathname: context.pathname ?? "/",
    search: context.search ?? "",
    userRole: context.userRole ?? "—",
  };

  if (!root) return {
    ...reportContext, breakdowns: [], factGroups: [], metrics: [], pageLimited: false, recordGroups: [],
    signals: [], tables: [], trends: [], visibleRowCount: 0,
  };

  const tables = collectTables(root);
  return {
    ...reportContext,
    breakdowns: collectBreakdowns(root),
    factGroups: collectFactGroups(root),
    metrics: collectMetrics(root),
    pageLimited: root.querySelector(".pagination") !== null,
    recordGroups: collectRecordGroups(root),
    signals: collectSignals(root),
    tables,
    trends: collectTrends(root),
    visibleRowCount: tables.reduce((total, table) => total + table.rows.length, 0),
  };
}

export function buildReportFilters(search: string, locale: Locale): ReportFilter[] {
  const copy = REPORT_COPY[locale];
  const filters: ReportFilter[] = [];
  for (const [key, value] of new URLSearchParams(search).entries()) {
    if (!value) continue;
    filters.push({
      label: key === "page" ? copy.page : key === "pageSize" ? copy.pageSize : FILTER_LABELS[locale][key] ?? humanizeKey(key),
      value: humanizeValue(value, locale),
    });
  }
  return filters;
}

export function DashboardReportDocument({ dateLocale, locale, snapshot }: {
  dateLocale: "en-US" | "ko-KR";
  locale: Locale;
  snapshot: DashboardReportSnapshot;
}) {
  const copy = REPORT_COPY[locale];
  const filters = buildReportFilters(snapshot.search, locale);
  const reportId = `EDR-${snapshot.generatedAt.toISOString().replace(/[-:]/g, "").slice(0, 15)}Z`;
  const overviewBreakdowns = snapshot.breakdowns.slice(0, 2);
  const remainingBreakdowns = snapshot.breakdowns.slice(2);
  const remainingRecordGroups = [...snapshot.recordGroups];
  const pages: ReportPage[] = [{
    content: <ReportOverview breakdowns={overviewBreakdowns} dateLocale={dateLocale} filters={filters} locale={locale} reportId={reportId} snapshot={snapshot} />,
    key: "overview",
    title: copy.executiveSummary,
  }];

  for (const [index, group] of chunk(remainingBreakdowns, 3).entries()) {
    const recordIndex = index === 0 ? remainingRecordGroups.findIndex((recordGroup) => recordGroup.records.length <= 6) : -1;
    const recordGroup = recordIndex >= 0 ? remainingRecordGroups.splice(recordIndex, 1)[0] : undefined;
    const scope = commonScope(recordGroup ? [...group, recordGroup] : group);
    pages.push({
      content: <div className="report-evidence-stack">
        <div className="report-breakdown-grid">{group.map((breakdown) => <ReportBreakdownCard breakdown={breakdown} key={`${breakdown.title}-${breakdown.scope}`} locale={locale} />)}</div>
        {recordGroup ? <section className="report-inline-records"><h3>{recordGroup.title}</h3><ReportRecords records={recordGroup.records} /></section> : null}
      </div>,
      key: `breakdowns-${index}`,
      ...(scope ? { scope } : {}),
      title: locale === "KO" ? "핵심 근거" : "Key evidence",
    });
  }

  for (const trend of snapshot.trends) for (const [index, trendPart] of chunkTrend(trend, 10).entries()) pages.push({
    content: <ReportTrend trend={trendPart} />,
    key: `trend-${trend.title}-${index}`,
    scope: trend.scope,
    title: trend.title,
  });

  for (const group of remainingRecordGroups) for (const [index, records] of chunk(group.records, 8).entries()) pages.push({
    content: <ReportRecords records={records} />,
    key: `records-${group.title}-${index}`,
    scope: group.scope,
    title: group.title,
  });

  for (const group of snapshot.factGroups) for (const [index, items] of chunk(group.items, 18).entries()) pages.push({
    content: <ReportFacts items={items} />,
    key: `facts-${group.title}-${index}`,
    scope: group.scope,
    title: group.title,
  });

  for (const table of snapshot.tables) {
    const rowsPerPage = table.columns.length > 8 ? 7 : table.columns.length > 5 ? 9 : 12;
    for (const [index, rows] of chunk(table.rows, rowsPerPage).entries()) pages.push({
      content: <ReportTable columns={table.columns} rows={rows} />,
      key: `table-${table.title}-${index}`,
      scope: table.scope,
      title: table.title,
    });
  }

  return <article className="dashboard-report-document">{pages.map((page, index) => <ReportSheet
    copy={copy} index={index} key={page.key} page={page} snapshot={snapshot} total={pages.length}
  />)}</article>;
}

export function DashboardReportPreview({ dateLocale, locale, snapshot }: {
  dateLocale: "en-US" | "ko-KR";
  locale: Locale;
  snapshot: DashboardReportSnapshot;
}) {
  return <div className="report-preview-frame"><div className="report-preview-canvas">
    <DashboardReportDocument dateLocale={dateLocale} locale={locale} snapshot={snapshot} />
  </div></div>;
}

function ReportSheet({ copy, index, page, snapshot, total }: {
  copy: (typeof REPORT_COPY)[Locale];
  index: number;
  page: ReportPage;
  snapshot: DashboardReportSnapshot;
  total: number;
}) {
  return <section className="report-sheet">
    {index === 0 ? null : <header className="report-sheet-header"><div><span>{copy.documentType}</span><h2>{page.title}</h2></div>{page.scope ? <ReportScopeBadge copy={copy} scope={page.scope} /> : null}</header>}
    <div className={index === 0 ? "report-sheet-content report-overview-content" : "report-sheet-content"}>{page.content}</div>
    <footer className="report-folio"><span>{snapshot.pathname}{snapshot.search}</span><strong>{index + 1} / {total}</strong></footer>
  </section>;
}

function ReportOverview({ breakdowns, dateLocale, filters, locale, reportId, snapshot }: {
  breakdowns: DashboardReportBreakdown[];
  dateLocale: "en-US" | "ko-KR";
  filters: ReportFilter[];
  locale: Locale;
  reportId: string;
  snapshot: DashboardReportSnapshot;
}) {
  const copy = REPORT_COPY[locale];
  const summaries = buildSummary(snapshot, locale);
  const scopes: DashboardReportScope[] = ["current-snapshot", "selected-period", "current-view"];
  const metricGroups = scopes.map((scope) => ({ scope, values: snapshot.metrics.filter((metric) => metric.scope === scope) })).filter((group) => group.values.length);

  return <>
    <header className="report-masthead"><div><span>{copy.documentType}</span><h1>{snapshot.pageTitle}</h1></div><strong>EDR Console</strong></header>
    <dl className="report-metadata">
      <div><dt>{copy.reportId}</dt><dd>{reportId}</dd></div>
      <div><dt>{copy.generated}</dt><dd>{snapshot.generatedAt.toLocaleString(dateLocale)}</dd></div>
      <div><dt>{copy.operator}</dt><dd>{snapshot.operator}</dd></div>
      <div><dt>{copy.userRole}</dt><dd>{snapshot.userRole}</dd></div>
    </dl>
    <section className="report-executive-summary">
      <h2>{copy.executiveSummary}</h2>
      {summaries.length ? <ul>{summaries.map((summary) => <li key={summary}>{summary}</li>)}</ul> : <p>{copy.empty}</p>}
    </section>
    {filters.length || snapshot.pageLimited ? <section aria-label={copy.appliedScope} className="report-filter-row">
      <strong>{copy.appliedScope}</strong>
      <div>{filters.map((filter, index) => <span key={`${filter.label}-${filter.value}-${index}`}><b>{filter.label}</b>{filter.value}</span>)}
        {snapshot.pageLimited ? <span className="report-visible-boundary">{copy.visibleBoundary(snapshot.visibleRowCount)}</span> : null}
      </div>
    </section> : null}
    {snapshot.signals.length ? <div className="report-signal-grid">{snapshot.signals.map((signal) => <ReportSignalCard copy={copy} key={signal.label} signal={signal} />)}</div> : null}
    {metricGroups.length ? <div className="report-metric-groups">{metricGroups.map((group) => <section key={group.scope}>
      <header><h3>{scopeLabel(group.scope, copy)}</h3></header>
      <div className="report-metric-grid">{group.values.map((metric) => <article key={`${metric.label}-${metric.value}`}>
        <span>{metric.label}</span><strong>{metric.value}</strong>{metric.detail ? <small>{metric.detail}</small> : null}
      </article>)}</div>
    </section>)}</div> : null}
    {breakdowns.length ? <div className="report-overview-breakdowns">{breakdowns.map((breakdown) => <ReportBreakdownCard breakdown={breakdown} compact key={`${breakdown.title}-${breakdown.scope}`} locale={locale} />)}</div> : null}
  </>;
}

function ReportSignalCard({ copy, signal }: { copy: (typeof REPORT_COPY)[Locale]; signal: DashboardReportSignal }) {
  return <section className="report-signal-card">
    <header><div><span>{scopeLabel(signal.scope, copy)}</span><h3>{signal.label}</h3></div>{signal.status ? <i>{signal.status}</i> : null}</header>
    <strong>{signal.value}</strong>
    {signal.details.length ? <ul>{signal.details.map((detail) => <li key={detail}>{detail}</li>)}</ul> : null}
  </section>;
}

function ReportBreakdownCard({ breakdown, compact = false, locale }: { breakdown: DashboardReportBreakdown; compact?: boolean; locale: Locale }) {
  const maximum = Math.max(...breakdown.rows.map((row) => row.count), 1);
  return <section className={compact ? "report-breakdown-card compact" : "report-breakdown-card"}>
    <header><h3>{breakdown.title}</h3><ReportScopeBadge copy={REPORT_COPY[locale]} scope={breakdown.scope} /></header>
    <div className="report-bars">{breakdown.rows.map((row) => {
      const share = row.count > 0 ? Math.max((row.count / maximum) * 100, 2) : 0;
      return <div className={`report-bar tone-${row.tone}`} key={`${row.label}-${row.value}`}>
        <div><span>{row.label}</span><strong>{row.value}</strong>{row.detail ? <small>{row.detail}</small> : null}</div>
        <i><b style={{ "--report-share": `${share}%` } as CSSProperties} /></i>
      </div>;
    })}</div>
  </section>;
}

function ReportTrend({ trend }: { trend: DashboardReportTrend }) {
  const maximum = Math.max(...trend.series.flatMap((series) => series.values.filter((value): value is number => value !== null)), 1);
  const middleIndex = Math.floor((trend.categories.length - 1) / 2);
  const axisLabels = [0, middleIndex, trend.categories.length - 1].filter((value, index, values) => value >= 0 && values.indexOf(value) === index);
  const chartHeight = trend.categories.length <= 4 ? 320 : trend.categories.length <= 7 ? 270 : 230;
  return <div className="report-trend" style={{ "--report-chart-height": `${chartHeight}px` } as CSSProperties}>
    <div className="report-trend-legend">{trend.series.map((series) => <span className={`tone-${series.tone}`} key={series.label}><i />{series.label}</span>)}</div>
    <svg aria-label={trend.title} className="report-trend-chart" role="img" viewBox="0 0 820 210">
      <path className="report-chart-grid" d="M54 24H802 M54 99H802 M54 174H802" />
      <g className="report-chart-y-labels"><text x="6" y="28">{maximum}</text><text x="6" y="103">{Math.round(maximum / 2)}</text><text x="6" y="178">0</text></g>
      {trend.series.map((series) => <g className={`report-chart-series tone-${series.tone}`} key={series.label}>
        <path d={trendPath(series.values, maximum)} />
        {trendPoints(series.values, maximum).map((point) => <circle cx={point.x} cy={point.y} key={point.index} r="3.2"><title>{trend.categories[point.index]} · {series.label}: {point.value}</title></circle>)}
      </g>)}
      <g className="report-chart-x-labels">{axisLabels.map((index) => <text key={index} textAnchor={index === 0 ? "start" : index === trend.categories.length - 1 ? "end" : "middle"} x={trendX(index, trend.categories.length)} y="202">{trend.categories[index]}</text>)}</g>
    </svg>
    <ReportTable columns={[localeIndependentBucketLabel(trend), ...trend.series.map((series) => series.label)]} rows={trend.categories.map((category, index) => [category, ...trend.series.map((series) => formatReportNumber(series.values[index] ?? null))])} />
  </div>;
}

function ReportTable({ columns, rows }: { columns: string[]; rows: string[][] }) {
  return <div className="report-table-wrap"><table className="report-table">
    <thead><tr>{columns.map((column, index) => <th key={`${column}-${index}`} scope="col">{column}</th>)}</tr></thead>
    <tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{columns.map((_column, columnIndex) => <td key={columnIndex}>{row[columnIndex] || "—"}</td>)}</tr>)}</tbody>
  </table></div>;
}

function ReportFacts({ items }: { items: DashboardReportFactGroup["items"] }) {
  return <dl className="report-facts">{items.map((item, index) => <div key={`${item.label}-${index}`}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>;
}

function ReportRecords({ records }: { records: DashboardReportRecordGroup["records"] }) {
  return <ol className="report-records">{records.map((record, index) => <li key={`${record.label}-${index}`}>
    <span>{String(index + 1).padStart(2, "0")}</span>
    <div><strong>{record.label}</strong>{record.details.length ? <ul>{record.details.map((detail) => <li key={detail}>{detail}</li>)}</ul> : null}</div>
  </li>)}</ol>;
}

function ReportScopeBadge({ copy, scope }: { copy: (typeof REPORT_COPY)[Locale]; scope: DashboardReportScope }) {
  return <span className={`report-scope-badge scope-${scope}`}>{scopeLabel(scope, copy)}</span>;
}

function collectMetrics(root: HTMLElement): DashboardReportMetric[] {
  return Array.from(root.querySelectorAll<HTMLElement>(".kpi-card"))
    .map((card): DashboardReportMetric | null => {
      const label = directChildText(card, "SPAN", "kpi-icon");
      const value = directChildText(card, "STRONG");
      const detail = directChildText(card, "SMALL");
      return label && value ? { label, value, ...(detail ? { detail } : {}), scope: scopeForNode(card) } : null;
    })
    .filter((metric): metric is DashboardReportMetric => metric !== null)
    .slice(0, 12);
}

function collectSignals(root: HTMLElement): DashboardReportSignal[] {
  return Array.from(root.querySelectorAll<HTMLElement>(".edr-state-summary")).map((signal) => {
    const label = text(signal.querySelector<HTMLElement>(".eyebrow")) || "EDR state";
    const score = text(signal.querySelector<HTMLElement>(".edr-overall strong"));
    const status = text(signal.querySelector<HTMLElement>(".status-pill"));
    const axes = Array.from(signal.querySelectorAll<HTMLElement>(".edr-axis")).map((axis) => {
      const axisLabel = text(axis.querySelector<HTMLElement>("span"));
      const axisScore = text(axis.querySelector<HTMLElement>("strong"));
      const axisStatus = text(axis.querySelector<HTMLElement>("small"));
      return [axisLabel, axisScore ? `${axisScore}/100` : "", axisStatus].filter(Boolean).join(" · ");
    });
    const reasons = Array.from(signal.querySelectorAll<HTMLElement>(".edr-reason-block li")).map(text).filter(Boolean);
    return {
      details: [...axes, ...reasons].slice(0, 6),
      label,
      scope: scopeForNode(signal),
      ...(status ? { status } : {}),
      value: score ? `${score}/100` : "—",
    };
  });
}

function collectBreakdowns(root: HTMLElement): DashboardReportBreakdown[] {
  const lists = root.querySelectorAll<HTMLElement>(".severity-donut-legend, .fleet-risk-list, .sensor-health-legend, .sensor-breakdown-statuses");
  return Array.from(lists).map((list, listIndex) => {
    const sectionTitle = text(list.closest("section")?.querySelector<HTMLElement>("header h3"));
    const groupTitle = list.classList.contains("sensor-breakdown-statuses")
      ? text(list.closest(".sensor-breakdown-heading")?.querySelector<HTMLElement>(":scope > strong"))
      : "";
    const panelTitle = text(list.closest(".panel")?.querySelector<HTMLElement>(".panel-heading h2"));
    const figureLabel = list.closest("figure")?.getAttribute("aria-label") ?? "";
    const titleParts = [panelTitle, sectionTitle, groupTitle, figureLabel].filter((value, index, values) => value && values.indexOf(value) === index);
    const rows = Array.from(list.children).map((item) => {
      const element = item as HTMLElement;
      const label = text(element.querySelector<HTMLElement>("span"));
      const value = text(element.querySelector<HTMLElement>("strong"));
      const detail = text(element.querySelector<HTMLElement>("small"));
      return {
        count: parseCount(value),
        ...(detail ? { detail } : {}),
        label: label || `Item ${listIndex + 1}`,
        tone: toneFromClass(element.className),
        value: value || "0",
      };
    });
    return { rows, scope: scopeForNode(list), title: titleParts.join(" · ") || `Distribution ${listIndex + 1}` };
  }).filter((breakdown) => breakdown.rows.length > 0);
}

function collectTrends(root: HTMLElement): DashboardReportTrend[] {
  return Array.from(root.querySelectorAll<HTMLElement>(".detection-activity-tables")).map((wrapper, wrapperIndex) => {
    const tables = Array.from(wrapper.querySelectorAll<HTMLTableElement>("table"));
    const categoryOrder: string[] = [];
    const series: DashboardReportTrendSeries[] = [];

    for (const [tableIndex, table] of tables.entries()) {
      const caption = text(table.querySelector<HTMLElement>("caption")) || `Series ${tableIndex + 1}`;
      const headers = Array.from(table.querySelectorAll<HTMLElement>("thead th")).map(cleanCell);
      const valueHeaders = headers.slice(1);
      const rows = Array.from(table.querySelectorAll<HTMLTableRowElement>("tbody tr")).map((row) => Array.from(row.cells).map(cleanCell));
      for (const row of rows) if (row[0] && !categoryOrder.includes(row[0])) categoryOrder.push(row[0]);
      for (let columnIndex = 1; columnIndex < Math.max(headers.length, 2); columnIndex += 1) {
        const valueMap = new Map(rows.map((row) => [row[0] ?? "", parseNullableCount(row[columnIndex])]));
        const label = valueHeaders.length > 1 ? `${caption} · ${valueHeaders[columnIndex - 1] ?? columnIndex}` : caption;
        series.push({
          label,
          tone: ["events", "alerts", "incidents-open", "incidents-closed"][series.length % 4] ?? "events",
          values: categoryOrder.map((category) => valueMap.get(category) ?? null),
        });
      }
    }

    for (const trendSeries of series) {
      if (trendSeries.values.length < categoryOrder.length) trendSeries.values.push(...Array(categoryOrder.length - trendSeries.values.length).fill(null));
    }

    return {
      categories: categoryOrder,
      scope: scopeForNode(wrapper),
      series,
      title: text(wrapper.closest(".chart-frame")?.querySelector<HTMLElement>(":scope > header h2"))
        || text(wrapper.closest(".panel")?.querySelector<HTMLElement>(".panel-heading h2"))
        || text(wrapper.closest("[data-overview-block]")?.querySelector<HTMLElement>(".panel-heading h2"))
        || `Trend ${wrapperIndex + 1}`,
    };
  }).filter((trend) => trend.categories.length > 0 && trend.series.length > 0);
}

function collectTables(root: HTMLElement): DashboardReportTable[] {
  return Array.from(root.querySelectorAll<HTMLTableElement>("table"))
    .filter((table) => table.closest(".detection-activity-tables") === null)
    .map((table, index) => {
      const columns = Array.from(table.querySelectorAll<HTMLElement>("thead th")).map(cleanCell);
      const rows = Array.from(table.querySelectorAll<HTMLTableRowElement>("tbody tr")).map((row) => Array.from(row.cells).map(cleanCell));
      const caption = text(table.querySelector<HTMLElement>("caption"));
      const panelTitle = text(table.closest(".panel")?.querySelector<HTMLElement>(".panel-heading h2"));
      const sectionTitle = text(table.closest(".detail-ledger-section")?.querySelector<HTMLElement>(":scope > header h2"));
      return {
        columns: columns.length ? columns : Array.from({ length: Math.max(...rows.map((row) => row.length), 0) }, (_, columnIndex) => `Column ${columnIndex + 1}`),
        rows,
        scope: scopeForNode(table),
        title: caption || sectionTitle || panelTitle || `Table ${index + 1}`,
      };
    })
    .filter((table) => table.columns.length > 0 && table.rows.length > 0);
}

function collectFactGroups(root: HTMLElement): DashboardReportFactGroup[] {
  return Array.from(root.querySelectorAll<HTMLElement>(".definition-grid, .detail-fact-list")).map((group, index) => {
    const items = Array.from(group.children).map((item) => ({
      label: text(item.querySelector<HTMLElement>("dt")),
      value: text(item.querySelector<HTMLElement>("dd")),
    })).filter((item) => item.label && item.value);
    const sectionTitle = text(group.closest(".detail-ledger-section")?.querySelector<HTMLElement>(":scope > header h2"));
    const panelTitle = text(group.closest(".panel")?.querySelector<HTMLElement>(".panel-heading h2"));
    return { items, scope: scopeForNode(group), title: sectionTitle || panelTitle || `Details ${index + 1}` };
  }).filter((group) => group.items.length > 0);
}

function collectRecordGroups(root: HTMLElement): DashboardReportRecordGroup[] {
  const selectors = ".risk-endpoint-ranking, .incident-queue-list, .guidance-list, .risk-factor-list";
  return Array.from(root.querySelectorAll<HTMLElement>(selectors)).map((group, index) => {
    const records = Array.from(group.children).map((item) => {
      const element = item as HTMLElement;
      const label = text(element.querySelector<HTMLElement>("a, .queue-primary > strong, :scope > strong")) || text(element).slice(0, 120);
      const details = Array.from(element.querySelectorAll<HTMLElement>("small, .status-pill, .incident-state, .incident-alert-count, time, .risk-ranking-metrics > div"))
        .filter((detail) => !(detail.matches("small") && detail.closest(".risk-ranking-metrics")))
        .map((detail) => detail.matches(".risk-ranking-metrics > div") ? joinedChildText(detail) : text(detail))
        .filter((value, detailIndex, values) => value && value !== label && values.indexOf(value) === detailIndex)
        .slice(0, 6);
      return { details, label };
    }).filter((record) => record.label);
    const panelTitle = text(group.closest(".panel")?.querySelector<HTMLElement>(".panel-heading h2"));
    const ariaLabel = group.getAttribute("aria-label") ?? "";
    return { records, scope: scopeForNode(group), title: panelTitle || ariaLabel || `Records ${index + 1}` };
  }).filter((group) => group.records.length > 0);
}

function scopeForNode(node: Element): DashboardReportScope {
  const block = node.closest<HTMLElement>("[data-overview-block]")?.dataset.overviewBlock;
  if (block && CURRENT_SNAPSHOT_BLOCKS.has(block)) return "current-snapshot";
  if (block && SELECTED_PERIOD_BLOCKS.has(block)) return "selected-period";
  const anchor = node.matches("a") ? node : node.closest("a");
  const href = anchor?.getAttribute("href") ?? "";
  if (TIME_QUERY_KEYS.some((key) => href.includes(`${key}=`))) return "selected-period";
  return "current-view";
}

function buildSummary(snapshot: DashboardReportSnapshot, locale: Locale): string[] {
  const summaries: string[] = [];
  const signal = snapshot.signals[0];
  if (signal) summaries.push(locale === "KO"
    ? `${signal.label} ${signal.value}${signal.status ? ` · ${signal.status}` : ""}`
    : `${signal.label}: ${signal.value}${signal.status ? ` · ${signal.status}` : ""}`);

  for (const scope of ["current-snapshot", "selected-period", "current-view"] as const) {
    const values = snapshot.metrics.filter((metric) => metric.scope === scope);
    if (!values.length || summaries.length >= 3) continue;
    summaries.push(`${scopeLabel(scope, REPORT_COPY[locale])}: ${values.map((metric) => `${metric.label} ${metric.value}`).join(" · ")}`);
  }
  if (snapshot.pageLimited && summaries.length < 3) summaries.push(REPORT_COPY[locale].visibleBoundary(snapshot.visibleRowCount));
  return summaries.slice(0, 3);
}

function scopeLabel(scope: DashboardReportScope, copy: (typeof REPORT_COPY)[Locale]): string {
  if (scope === "selected-period") return copy.selectedPeriod;
  if (scope === "current-snapshot") return copy.currentSnapshot;
  return copy.currentView;
}

function commonScope(items: Array<{ scope: DashboardReportScope }>): DashboardReportScope | undefined {
  const first = items[0]?.scope;
  return first && items.every((item) => item.scope === first) ? first : undefined;
}

function chunkTrend(trend: DashboardReportTrend, size: number): DashboardReportTrend[] {
  return chunk(trend.categories, size).map((categories, chunkIndex) => ({
    ...trend,
    categories,
    series: trend.series.map((series) => ({ ...series, values: series.values.slice(chunkIndex * size, (chunkIndex + 1) * size) })),
  }));
}

function trendPath(values: Array<number | null>, maximum: number): string {
  return values.map((value, index) => value === null ? "" : `${index === 0 || values[index - 1] === null ? "M" : "L"}${trendX(index, values.length)},${trendY(value, maximum)}`).join(" ");
}

function trendPoints(values: Array<number | null>, maximum: number): Array<{ index: number; value: number; x: number; y: number }> {
  return values.flatMap((value, index) => value === null ? [] : [{ index, value, x: trendX(index, values.length), y: trendY(value, maximum) }]);
}

function trendX(index: number, length: number): number {
  return length <= 1 ? 428 : 54 + (index * 748) / (length - 1);
}

function trendY(value: number, maximum: number): number {
  return 174 - (value / Math.max(maximum, 1)) * 150;
}

function localeIndependentBucketLabel(trend: DashboardReportTrend): string {
  return trend.categories.some((category) => /\d{4}|\d{1,2}[:/-]\d{1,2}/.test(category)) ? "Bucket" : "Category";
}

function formatReportNumber(value: number | null): string {
  return value === null ? "—" : value.toLocaleString();
}

function directChildText(element: HTMLElement, tagName: string, excludedClass?: string): string {
  const child = Array.from(element.children).find((candidate) => candidate.tagName === tagName && (!excludedClass || !candidate.classList.contains(excludedClass)));
  return text(child);
}

function joinedChildText(element: HTMLElement): string {
  return Array.from(element.children).map(text).filter(Boolean).join(" ") || text(element);
}

function text(node: Element | null | undefined): string {
  return (node?.textContent ?? "").replace(/\s+/g, " ").trim();
}

function cleanCell(node: Element): string {
  return text(node).replace(/[↕↓↑]+$/u, "").trim();
}

function parseCount(value: string): number {
  return Number(value.replace(/[^\d.-]/g, "")) || 0;
}

function parseNullableCount(value: string | undefined): number | null {
  if (!value || value.trim() === "—") return null;
  const parsed = Number(value.replace(/[^\d.-]/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function toneFromClass(className: string): string {
  return className.match(/tone-([a-z-]+)/)?.[1] ?? "neutral";
}

function chunk<T>(items: readonly T[], size: number): T[][] {
  const groups: T[][] = [];
  for (let index = 0; index < items.length; index += size) groups.push(items.slice(index, index + size));
  return groups;
}

function humanizeKey(value: string): string {
  return value.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function humanizeValue(value: string, locale: Locale): string {
  const presets: Record<Locale, Record<string, string>> = {
    EN: { LATEST_15M: "Latest 15 minutes", LATEST_1H: "Latest 1 hour", LATEST_24H: "Latest 24 hours", LATEST_7D: "Latest 7 days", CUSTOM: "Custom UTC range" },
    KO: { LATEST_15M: "최근 15분", LATEST_1H: "최근 1시간", LATEST_24H: "최근 24시간", LATEST_7D: "최근 7일", CUSTOM: "UTC 기간 직접 설정" },
  };
  return presets[locale][value] ?? value.replaceAll("_", " ");
}
