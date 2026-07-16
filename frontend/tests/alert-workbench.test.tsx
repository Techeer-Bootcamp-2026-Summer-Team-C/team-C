import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { api } from "../src/api/endpoints";
import { AuthProvider } from "../src/auth/AuthContext";
import type { AlertDetailDto, AlertDto, UserDto } from "../src/contracts";
import { LocaleProvider } from "../src/i18n/LocaleContext";
import { AlertDetailPage } from "../src/pages/AlertDetailPage";

const TIMESTAMP = "2026-07-15T03:00:00Z";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("WP-05 alert workbench", () => {
  it("keeps Save status separate from navigation", async () => {
    const update = arrangeApi();
    renderDetail("ADMIN");
    await screen.findByRole("heading", { name: "Alert 1" });

    fireEvent.change(screen.getByRole("combobox", { name: "Alert status" }), { target: { value: "IN_PROGRESS" } });
    fireEvent.click(screen.getByRole("button", { name: "Save status" }));

    await waitFor(() => expect(update).toHaveBeenCalledWith(1, { status: "IN_PROGRESS" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/alerts/1");
    expect(await screen.findByText("Alert workflow state saved.")).toBeInTheDocument();
  });

  it("saves and moves to the next unresolved Alert while replacing selected URL state", async () => {
    const update = arrangeApi();
    renderDetail("ADMIN");
    await screen.findByRole("heading", { name: "Alert 1" });
    const next = await screen.findByRole("button", { name: "Submit & Next" });
    await waitFor(() => expect(next).toBeEnabled());

    fireEvent.click(next);

    await waitFor(() => expect(update).toHaveBeenCalledWith(1, { status: "OPEN" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/alerts/2?status=OPEN&sortBy=priority&selected=2"));
    expect(await screen.findByRole("heading", { name: "Alert 2" })).toBeInTheDocument();
  });

  it("keeps workflow controls hidden for VIEWER and guidance explicitly read-only", async () => {
    arrangeApi();
    renderDetail("VIEWER");
    await screen.findByRole("heading", { name: "Alert 1" });

    expect(screen.queryByRole("button", { name: "Save status" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit & Next" })).not.toBeInTheDocument();
    expect(screen.getByText("Read-only steps from PROC-001 v3")).toBeInTheDocument();
    expect(screen.getByText("Manual action")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});

function arrangeApi() {
  vi.spyOn(api, "alert").mockImplementation(async (alertId) => envelope(detail(alertId)));
  vi.spyOn(api, "alerts").mockResolvedValue(envelope({
    items: [summary(1, "OPEN"), summary(2, "IN_PROGRESS"), summary(3, "RESOLVED")],
    page: 1,
    size: 500,
    total: 3,
    totalPages: 1,
  }));
  return vi.spyOn(api, "updateAlert").mockImplementation(async (alertId, body) => envelope(summary(alertId, body.status)));
}

function renderDetail(role: UserDto["role"]) {
  sessionStorage.setItem("edr.authSession", JSON.stringify({
    token: "alert-workbench-token",
    user: { userId: 1, loginId: "operator", name: "Operator", role, status: "ACTIVE", locale: "EN" },
    expiresAt: Date.now() + 60_000,
  }));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><AuthProvider><LocaleProvider><MemoryRouter initialEntries={["/alerts/1?status=OPEN&sortBy=priority&selected=1"]}><Routes><Route path="/alerts/:alertId" element={<><AlertDetailPage /><LocationProbe /></>} /></Routes></MemoryRouter></LocaleProvider></AuthProvider></QueryClientProvider>);
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

function detail(alertId: number): AlertDetailDto {
  return {
    ...summary(alertId, "OPEN"),
    sourceEvent: null,
    incidents: [],
    responseGuidance: [{ order: 1, title: "Preserve evidence", description: "Capture the process tree before remediation.", requiresManualAction: true }],
  };
}

function summary(alertId: number, status: AlertDto["status"]): AlertDto {
  return {
    alertId,
    endpointId: 1001,
    eventId: `event-${alertId}`,
    eventOccurredAt: TIMESTAMP,
    batchId: null,
    agentId: "agent-1",
    ruleCode: "PROC-001",
    ruleName: "Suspicious process",
    ruleVersion: 3,
    mitreTacticCode: "TA0002",
    mitreTacticName: "Execution",
    mitreTechniqueCode: "T1059",
    mitreTechniqueName: "Command and Scripting Interpreter",
    title: `Alert ${alertId}`,
    summary: "Suspicious process activity",
    severity: alertId === 1 ? "CRITICAL" : "HIGH",
    riskScore: alertId === 1 ? 95 : 80,
    status,
    detectedAt: TIMESTAMP,
    createdAt: TIMESTAMP,
    updatedAt: TIMESTAMP,
  };
}

function envelope<Data>(data: Data) {
  return { data, meta: { requestId: "req_alert_workbench" } };
}
