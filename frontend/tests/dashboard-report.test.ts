import { afterEach, describe, expect, it } from "vitest";
import { buildReportFilters, collectDashboardReport } from "../src/features/dashboardReport";

afterEach(() => {
  document.body.replaceChildren();
});

describe("dashboard report", () => {
  it("collects a stable summary from the currently rendered evidence", () => {
    document.body.innerHTML = `
      <main id="report-root">
        <header class="page-header"><h1>Overview</h1></header>
        <a class="kpi-card accent"><span class="kpi-icon"></span><span>Total alerts</span><strong>42</strong><small>Selected range</small></a>
        <article class="kpi-card critical"><span class="kpi-icon"></span><span>Critical alerts</span><strong>7</strong><small>Needs review</small></article>
        <section class="panel"><header class="panel-heading"><h2>Detection activity</h2></header><table><tbody><tr></tr><tr></tr></tbody></table></section>
        <section class="panel"><header class="panel-heading"><h2>Detection activity</h2></header><table><tbody><tr></tr></tbody></table></section>
      </main>
    `;
    const generatedAt = new Date("2026-07-21T03:04:05.000Z");
    const root = document.querySelector<HTMLElement>("#report-root");

    const snapshot = collectDashboardReport(root, generatedAt);

    expect(snapshot.generatedAt).toBe(generatedAt);
    expect(snapshot.metrics).toEqual([
      { label: "Total alerts", value: "42", detail: "Selected range" },
      { label: "Critical alerts", value: "7", detail: "Needs review" },
    ]);
    expect(snapshot.sectionTitles).toEqual(["Overview", "Detection activity"]);
    expect(snapshot.tableCount).toBe(2);
    expect(snapshot.visibleRowCount).toBe(3);
  });

  it("turns the current URL query into a localized report scope", () => {
    expect(buildReportFilters("?timePreset=LATEST_7D&severity=CRITICAL&page=2", "KO")).toEqual([
      { label: "조회 기간", value: "최근 7일" },
      { label: "심각도", value: "CRITICAL" },
      { label: "페이지", value: "2" },
    ]);
  });

  it("returns an explicit empty snapshot before page content is available", () => {
    const snapshot = collectDashboardReport(null);
    expect(snapshot.metrics).toEqual([]);
    expect(snapshot.sectionTitles).toEqual([]);
    expect(snapshot.tableCount).toBe(0);
    expect(snapshot.visibleRowCount).toBe(0);
  });
});
