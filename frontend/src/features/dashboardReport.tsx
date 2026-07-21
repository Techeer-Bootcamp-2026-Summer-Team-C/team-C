import type { Locale } from "../i18n/types";

export interface DashboardReportMetric {
  label: string;
  value: string;
  detail?: string;
}

export interface DashboardReportSnapshot {
  generatedAt: Date;
  metrics: DashboardReportMetric[];
  sectionTitles: string[];
  tableCount: number;
  visibleRowCount: number;
}

interface ReportFilter {
  label: string;
  value: string;
}

const REPORT_COPY = {
  EN: {
    documentType: "EDR OPERATIONS REPORT",
    summary: "Executive summary",
    keyMetrics: "KPI snapshot",
    includedSections: "Evidence index",
    appliedScope: "Technical scope",
    reportId: "Report ID",
    generated: "Generated",
    preparedBy: "Operator",
    accessRole: "Access role",
    source: "Route / query",
    coverage: "Rendered evidence",
    coverageValue: (tables: number, rows: number) => `${tables} tables · ${rows} visible rows`,
    evidence: "Evidence details",
    noSections: "Current page content",
    page: "Page",
    pageSize: "Page size",
  },
  KO: {
    documentType: "EDR 운영 리포트",
    summary: "Executive summary",
    keyMetrics: "KPI snapshot",
    includedSections: "Evidence index",
    appliedScope: "Technical scope",
    reportId: "Report ID",
    generated: "생성 시각",
    preparedBy: "Operator",
    accessRole: "Access role",
    source: "Route / Query",
    coverage: "Rendered evidence",
    coverageValue: (tables: number, rows: number) => `표 ${tables}개 · 현재 표시 행 ${rows}개`,
    evidence: "Evidence details",
    noSections: "현재 화면 내용",
    page: "페이지",
    pageSize: "페이지 크기",
  },
} as const;

const FILTER_LABELS: Record<Locale, Record<string, string>> = {
  EN: {
    timePreset: "Time range",
    from: "From (UTC)",
    to: "To (UTC)",
    endpointId: "Endpoint ID",
    endpointIds: "Endpoint IDs",
    severity: "Severity",
    status: "Status",
    riskLevel: "Risk level",
    osType: "Operating system",
    sortBy: "Sort by",
    sortOrder: "Sort order",
    q: "Search",
    processName: "Process name",
    eventType: "Event type",
    ruleCode: "Rule code",
    domain: "Domain",
  },
  KO: {
    timePreset: "조회 기간",
    from: "시작 (UTC)",
    to: "종료 (UTC)",
    endpointId: "Endpoint ID",
    endpointIds: "Endpoint ID 목록",
    severity: "심각도",
    status: "상태",
    riskLevel: "Risk 등급",
    osType: "운영체제",
    sortBy: "정렬 기준",
    sortOrder: "정렬 순서",
    q: "검색어",
    processName: "Process 이름",
    eventType: "Event 유형",
    ruleCode: "Rule 코드",
    domain: "Domain",
  },
};

export function collectDashboardReport(root: HTMLElement | null, generatedAt = new Date()): DashboardReportSnapshot {
  if (!root) return { generatedAt, metrics: [], sectionTitles: [], tableCount: 0, visibleRowCount: 0 };

  const metrics = Array.from(root.querySelectorAll<HTMLElement>(".kpi-card"))
    .map((card): DashboardReportMetric | null => {
      const label = Array.from(card.children).find((child) => child.tagName === "SPAN" && !child.classList.contains("kpi-icon"))?.textContent?.trim();
      const value = Array.from(card.children).find((child) => child.tagName === "STRONG")?.textContent?.trim();
      const detail = Array.from(card.children).find((child) => child.tagName === "SMALL")?.textContent?.trim();
      return label && value ? { label, value, ...(detail ? { detail } : {}) } : null;
    })
    .filter((metric): metric is DashboardReportMetric => metric !== null)
    .slice(0, 6);

  const sectionTitles = uniqueText(root.querySelectorAll<HTMLElement>(".panel-heading h2, .detail-ledger-section > header h2, .page-header h1"), 10);
  const tables = Array.from(root.querySelectorAll("table"));

  return {
    generatedAt,
    metrics,
    sectionTitles,
    tableCount: tables.length,
    visibleRowCount: tables.reduce((count, table) => count + table.querySelectorAll("tbody tr").length, 0),
  };
}

export function buildReportFilters(search: string, locale: Locale): ReportFilter[] {
  const copy = REPORT_COPY[locale];
  const values = new URLSearchParams(search);
  const filters: ReportFilter[] = [];

  for (const [key, value] of values.entries()) {
    if (!value) continue;
    filters.push({
      label: key === "page" ? copy.page : key === "pageSize" ? copy.pageSize : FILTER_LABELS[locale][key] ?? humanizeKey(key),
      value: humanizeValue(value, locale),
    });
  }

  return filters;
}

export function DashboardReportHeader({
  dateLocale,
  locale,
  pageTitle,
  pathname,
  search,
  snapshot,
  userName,
  userRole,
}: {
  dateLocale: "en-US" | "ko-KR";
  locale: Locale;
  pageTitle: string;
  pathname: string;
  search: string;
  snapshot: DashboardReportSnapshot;
  userName: string | undefined;
  userRole: string | undefined;
}) {
  const copy = REPORT_COPY[locale];
  const filters = buildReportFilters(search, locale);
  const generatedAt = snapshot.generatedAt.toLocaleString(dateLocale);
  const reportId = `EDR-${snapshot.generatedAt.toISOString().replace(/[-:]/g, "").slice(0, 15)}Z`;

  return <>
    <article aria-hidden="true" className="print-report-header print-report-only">
      <header className="print-report-title">
        <div><span>{copy.documentType}</span><h1>{pageTitle}</h1></div>
        <strong>EDR Console</strong>
      </header>
      <dl className="print-report-metadata">
        <div><dt>{copy.reportId}</dt><dd>{reportId}</dd></div>
        <div><dt>{copy.generated}</dt><dd>{generatedAt}</dd></div>
        <div><dt>{copy.preparedBy}</dt><dd>{userName ?? "—"}</dd></div>
        <div><dt>{copy.accessRole}</dt><dd>{userRole ?? "—"}</dd></div>
        <div><dt>{copy.source}</dt><dd>{pathname}{search}</dd></div>
        <div><dt>{copy.coverage}</dt><dd>{copy.coverageValue(snapshot.tableCount, snapshot.visibleRowCount)}</dd></div>
      </dl>
      {filters.length ? <section className="print-report-scope">
        <h2>{copy.appliedScope}</h2>
        <dl>{filters.map((filter, index) => <div key={`${filter.label}-${filter.value}-${index}`}><dt>{filter.label}</dt><dd>{filter.value}</dd></div>)}</dl>
      </section> : null}
      <section className="print-report-summary">
        <h2>{copy.summary}</h2>
        {snapshot.metrics.length ? <div className="print-report-metrics">{snapshot.metrics.map((metric) => <article key={`${metric.label}-${metric.value}`}><span>{metric.label}</span><strong>{metric.value}</strong>{metric.detail ? <small>{metric.detail}</small> : null}</article>)}</div> : null}
        <div className="print-report-sections"><h3>{copy.includedSections}</h3><p>{snapshot.sectionTitles.length ? snapshot.sectionTitles.join(" · ") : copy.noSections}</p></div>
      </section>
      <footer><span>{copy.evidence}</span></footer>
    </article>
  </>;
}

export function DashboardReportPreview({ locale, snapshot }: { locale: Locale; snapshot: DashboardReportSnapshot }) {
  const copy = REPORT_COPY[locale];
  return <>
    <div className="report-preview-stats">
      <div><span>{copy.keyMetrics}</span><strong>{snapshot.metrics.length}</strong></div>
      <div><span>{copy.includedSections}</span><strong>{snapshot.sectionTitles.length}</strong></div>
      <div><span>{copy.coverage}</span><strong>{copy.coverageValue(snapshot.tableCount, snapshot.visibleRowCount)}</strong></div>
    </div>
  </>;
}

function uniqueText(nodes: NodeListOf<HTMLElement>, limit: number): string[] {
  const values = new Set<string>();
  for (const node of nodes) {
    const value = node.textContent?.trim();
    if (value) values.add(value);
    if (values.size === limit) break;
  }
  return Array.from(values);
}

function humanizeKey(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replaceAll("_", " ")
    .replace(/^./, (letter) => letter.toUpperCase());
}

function humanizeValue(value: string, locale: Locale): string {
  const presets: Record<Locale, Record<string, string>> = {
    EN: {
      LATEST_15M: "Latest 15 minutes",
      LATEST_1H: "Latest 1 hour",
      LATEST_24H: "Latest 24 hours",
      LATEST_7D: "Latest 7 days",
      CUSTOM: "Custom UTC range",
    },
    KO: {
      LATEST_15M: "최근 15분",
      LATEST_1H: "최근 1시간",
      LATEST_24H: "최근 24시간",
      LATEST_7D: "최근 7일",
      CUSTOM: "UTC 기간 직접 설정",
    },
  };
  const preset = presets[locale][value];
  return preset ?? value.replaceAll("_", " ");
}
