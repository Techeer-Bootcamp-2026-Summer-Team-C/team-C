import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DetectionActivityChart, DetectionActivityTable } from "../src/components/charts";
import { AuthProvider } from "../src/auth/AuthContext";
import { OVERVIEW_WIDGET_REGISTRY } from "../src/features/overviewWidgetRegistry";
import { LocaleProvider } from "../src/i18n/LocaleContext";
import type { EndpointDto } from "../src/contracts";
import { OverviewEndpointSelect, readOverviewEndpointId } from "../src/pages/OverviewPage";

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
});

describe("WP-04 overview registry and detection activity", () => {
  it("owns exactly the ten approved dashboard blocks in display order", () => {
    expect(OVERVIEW_WIDGET_REGISTRY.map((widget) => widget.id)).toEqual([
      "edr-state",
      "kpi-alerts",
      "kpi-open-incidents",
      "kpi-high-risk-endpoints",
      "kpi-event-failures",
      "detection-activity",
      "alert-severity",
      "endpoint-risk",
      "highest-risk-endpoints",
      "incident-queue",
    ]);
    expect(OVERVIEW_WIDGET_REGISTRY).toHaveLength(10);
  });

  it("renders all three server-provided activity series and an accessible table fallback", () => {
    const events = [{ bucketStartAt: "2026-07-15T00:00:00Z", count: 12 }];
    const alerts = [{ bucketStartAt: "2026-07-15T00:00:00Z", count: 4 }];
    const incidents = [{ bucketStartAt: "2026-07-15T00:00:00Z", openCount: 2, closedCount: 1 }];
    window.sessionStorage.setItem("edr.authSession", JSON.stringify({
      token: "overview-test-token",
      user: { userId: 1, loginId: "admin", name: "Administrator", role: "ADMIN", status: "ACTIVE", locale: "EN" },
      expiresAt: Date.now() + 60_000,
    }));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><AuthProvider><LocaleProvider><DetectionActivityChart alerts={alerts} events={events} incidents={incidents} /><DetectionActivityTable alerts={alerts} events={events} incidents={incidents} /></LocaleProvider></AuthProvider></QueryClientProvider>);

    expect(screen.getByRole("region", { name: "Events" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Alerts" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Incidents" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Events" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Alerts" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Incidents" })).toBeInTheDocument();
  });

  it("offers all and individual Endpoint scopes and emits the selected id", () => {
    window.sessionStorage.setItem("edr.authSession", JSON.stringify({
      token: "overview-test-token",
      user: { userId: 1, loginId: "admin", name: "Administrator", role: "ADMIN", status: "ACTIVE", locale: "EN" },
      expiresAt: Date.now() + 60_000,
    }));
    const onChange = vi.fn();
    const endpointOptions = [
      { endpointId: 1, hostname: "SOC-WIN-01" } as EndpointDto,
      { endpointId: 2, hostname: "FINANCE-MAC-02" } as EndpointDto,
    ];
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><AuthProvider><LocaleProvider>
      <OverviewEndpointSelect endpointOptions={endpointOptions} onChange={onChange} selectedEndpointId={undefined} />
    </LocaleProvider></AuthProvider></QueryClientProvider>);

    const select = screen.getByRole("combobox", { name: "Endpoint scope" });
    expect(screen.getByRole("option", { name: "All endpoints" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "SOC-WIN-01 · ID 1" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "FINANCE-MAC-02 · ID 2" })).toBeInTheDocument();

    fireEvent.change(select, { target: { value: "2" } });
    fireEvent.change(select, { target: { value: "" } });
    expect(onChange).toHaveBeenNthCalledWith(1, 2);
    expect(onChange).toHaveBeenNthCalledWith(2, undefined);
  });

  it("reads only positive integer endpointId values from the Overview URL", () => {
    expect(readOverviewEndpointId(new URLSearchParams("endpointId=2"))).toBe(2);
    expect(readOverviewEndpointId(new URLSearchParams("endpointId=0"))).toBeUndefined();
    expect(readOverviewEndpointId(new URLSearchParams("endpointId=all"))).toBeUndefined();
  });
});
