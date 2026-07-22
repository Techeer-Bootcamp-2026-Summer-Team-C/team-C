import { createElement } from "react";
import { render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  buildReportFilters,
  collectDashboardReport,
  DashboardReportDocument,
} from "../src/features/dashboardReport";

afterEach(() => {
  document.body.replaceChildren();
});

describe("dashboard report", () => {
  it("freezes rendered evidence and keeps current snapshot separate from the selected period", () => {
    document.body.innerHTML = `
      <main id="report-root">
        <div data-overview-block="kpi-alerts">
          <a class="kpi-card accent" href="/alerts?timePreset=LATEST_24H"><span class="kpi-icon"></span><span>Total alerts</span><strong>42</strong><small>Selected range</small></a>
        </div>
        <div data-overview-block="kpi-high-risk-endpoints">
          <a class="kpi-card high" href="/endpoints"><span class="kpi-icon"></span><span>High-risk endpoints</span><strong>8</strong><small>Current risk snapshot</small></a>
        </div>
        <div data-overview-block="edr-state">
          <section class="edr-state-summary"><h2 class="eyebrow">Current EDR state</h2><div class="edr-overall"><strong>71</strong></div><span class="status-pill">Degraded</span><div class="edr-axis"><span>Threat level</span><strong>80</strong><small>High</small></div></section>
        </div>
        <div data-overview-block="alert-severity"><section class="panel"><header class="panel-heading"><h2>Alert severity</h2></header><ul class="severity-donut-legend"><li class="tone-critical"><span>Critical</span><strong>7</strong><small>16.7%</small></li><li class="tone-high"><span>High</span><strong>12</strong><small>28.6%</small></li></ul></section></div>
        <div data-overview-block="detection-activity"><section class="panel"><header class="panel-heading"><h2>Detection activity</h2></header><div class="detection-activity-tables"><table><caption>Events</caption><thead><tr><th>Bucket</th><th>Count</th></tr></thead><tbody><tr><td>10:00</td><td>10</td></tr><tr><td>11:00</td><td>14</td></tr></tbody></table></div></section></div>
        <section class="panel"><header class="panel-heading"><h2>Alert queue</h2></header><table><thead><tr><th>Alert ID</th><th>Severity</th></tr></thead><tbody><tr><td>101</td><td>Critical</td></tr><tr><td>102</td><td>High</td></tr></tbody></table></section>
        <nav class="pagination"></nav>
      </main>
    `;
    const generatedAt = new Date("2026-07-21T03:04:05.000Z");
    const root = document.querySelector<HTMLElement>("#report-root");

    const snapshot = collectDashboardReport(root, {
      generatedAt,
      operator: "operator-1",
      pageTitle: "Overview",
      pathname: "/",
      search: "?timePreset=LATEST_24H&page=2",
      userRole: "ANALYST",
    });

    expect(snapshot.metrics).toEqual([
      { label: "Total alerts", value: "42", detail: "Selected range", scope: "selected-period" },
      { label: "High-risk endpoints", value: "8", detail: "Current risk snapshot", scope: "current-snapshot" },
    ]);
    expect(snapshot.signals[0]).toMatchObject({ value: "71/100", status: "Degraded", scope: "current-snapshot" });
    expect(snapshot.breakdowns[0]).toMatchObject({ title: "Alert severity", scope: "selected-period" });
    expect(snapshot.trends[0]).toMatchObject({ title: "Detection activity", scope: "selected-period", categories: ["10:00", "11:00"] });
    expect(snapshot.tables).toHaveLength(1);
    expect(snapshot.visibleRowCount).toBe(2);
    expect(snapshot.pageLimited).toBe(true);

    const renderedValue = root?.querySelector<HTMLElement>(".kpi-card strong");
    if (renderedValue) renderedValue.textContent = "999";
    expect(snapshot.metrics[0]?.value).toBe("42");
  });

  it("renders the concise A4 document without the removed evidence copy", () => {
    document.body.innerHTML = `<main id="report-root"><table><thead><tr><th>ID</th></tr></thead><tbody><tr><td>7</td></tr></tbody></table><nav class="pagination"></nav></main>`;
    const snapshot = collectDashboardReport(document.querySelector<HTMLElement>("#report-root"), {
      generatedAt: new Date("2026-07-21T03:04:05.000Z"),
      pageTitle: "Alerts",
      pathname: "/alerts",
      search: "?page=2",
    });

    const view = render(createElement(DashboardReportDocument, { dateLocale: "en-US", locale: "EN", snapshot }));

    expect(view.container.querySelectorAll(".report-sheet").length).toBe(2);
    expect(view.container.textContent).toContain("Executive Summary");
    expect(view.container.textContent).toContain("Visible page · 1 rows");
    expect(view.container.textContent).not.toContain("Evidence index");
    expect(view.container.textContent).not.toContain("Rendered evidence");
    expect(view.container.textContent).not.toContain("UI Query Snapshot");
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
    expect(snapshot.tables).toEqual([]);
    expect(snapshot.trends).toEqual([]);
    expect(snapshot.visibleRowCount).toBe(0);
  });
});
