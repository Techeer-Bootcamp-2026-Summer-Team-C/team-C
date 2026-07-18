import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { createOverviewWidget } from "../src/features/overviewLayout/overviewLayoutModel";
import { OverviewLayoutProvider, useOverviewLayout } from "../src/features/overviewLayout/OverviewLayoutContext";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("Overview layout context", () => {
  it("creates, renames, selects, and deletes a dashboard with active fallback", async () => {
    render(<OverviewLayoutProvider userId={11}><LayoutProbe /></OverviewLayoutProvider>);
    expect(screen.getByTestId("active")).toHaveTextContent("default");

    await userEvent.click(screen.getByRole("button", { name: "create" }));
    const dashboardId = screen.getByTestId("active").textContent ?? "";
    expect(dashboardId).toMatch(/^dashboard-/);
    expect(screen.getByTestId("names")).toHaveTextContent("Investigation");
    expect(localStorage.getItem("edr.overviewActiveDashboard.v1.user.11")).toBe(dashboardId);

    await userEvent.click(screen.getByRole("button", { name: "move" }));
    const movedStore = JSON.parse(localStorage.getItem("edr.overviewDashboards.v1.user.11") ?? "{}");
    expect(movedStore.dashboards[0].widgets[0]).toMatchObject({ x: 4, y: 3, w: 4, h: 3 });

    await userEvent.click(screen.getByRole("button", { name: "rename" }));
    expect(screen.getByTestId("names")).toHaveTextContent("Priority view");
    await userEvent.click(screen.getByRole("button", { name: "delete" }));
    expect(screen.getByTestId("active")).toHaveTextContent("default");
    expect(screen.getByTestId("names")).toBeEmptyDOMElement();
  });

  it("reinitializes state when the provider is remounted for another user", async () => {
    const { rerender } = render(<OverviewLayoutProvider key="21" userId={21}><LayoutProbe /></OverviewLayoutProvider>);
    await userEvent.click(screen.getByRole("button", { name: "create" }));
    expect(screen.getByTestId("names")).toHaveTextContent("Investigation");

    rerender(<OverviewLayoutProvider key="22" userId={22}><LayoutProbe /></OverviewLayoutProvider>);
    expect(screen.getByTestId("active")).toHaveTextContent("default");
    expect(screen.getByTestId("names")).toBeEmptyDOMElement();
  });

  it("enforces one widget per type at create and update boundaries", async () => {
    render(<OverviewLayoutProvider userId={31}><LayoutProbe /></OverviewLayoutProvider>);
    await userEvent.click(screen.getByRole("button", { name: "create duplicates" }));
    let store = JSON.parse(localStorage.getItem("edr.overviewDashboards.v1.user.31") ?? "{}");
    expect(store.dashboards[0].widgets.map((widget: { type: string }) => widget.type)).toEqual(["kpi-alerts", "kpi-critical-alerts"]);

    await userEvent.click(screen.getByRole("button", { name: "update duplicates" }));
    store = JSON.parse(localStorage.getItem("edr.overviewDashboards.v1.user.31") ?? "{}");
    expect(store.dashboards[0].widgets.map((widget: { type: string }) => widget.type)).toEqual(["kpi-alerts", "kpi-critical-alerts", "kpi-open-incidents"]);
  });
});

function LayoutProbe() {
  const layout = useOverviewLayout();
  return <>
    <output data-testid="active">{layout.activeDashboardId}</output>
    <output data-testid="names">{layout.dashboards.map((dashboard) => dashboard.name).join(",")}</output>
    <button onClick={() => layout.createDashboard("Investigation", [createOverviewWidget("kpi-alerts")])} type="button">create</button>
    <button onClick={() => layout.activeDashboard && layout.updateDashboard(layout.activeDashboard.id, "Priority view", layout.activeDashboard.widgets)} type="button">rename</button>
    <button onClick={() => layout.activeDashboard && layout.updateDashboard(layout.activeDashboard.id, layout.activeDashboard.name, layout.activeDashboard.widgets.map((widget, index) => index === 0 ? { ...widget, x: 4, y: 3, w: 4, h: 3 } : widget))} type="button">move</button>
    <button onClick={() => layout.createDashboard("Deduplicated", [createOverviewWidget("kpi-alerts"), createOverviewWidget("kpi-alerts"), createOverviewWidget("kpi-critical-alerts")])} type="button">create duplicates</button>
    <button onClick={() => layout.activeDashboard && layout.updateDashboard(layout.activeDashboard.id, layout.activeDashboard.name, [...layout.activeDashboard.widgets, createOverviewWidget("kpi-alerts"), createOverviewWidget("kpi-open-incidents")])} type="button">update duplicates</button>
    <button onClick={() => layout.activeDashboard && layout.deleteDashboard(layout.activeDashboard.id)} type="button">delete</button>
  </>;
}
