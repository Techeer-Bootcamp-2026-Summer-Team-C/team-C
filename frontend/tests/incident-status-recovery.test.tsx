import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { api } from "../src/api/endpoints";
import { AuthProvider } from "../src/auth/AuthContext";
import type {
  AttackTimelineDto,
  IncidentDetailDto,
  IncidentDto,
  IncidentInvestigationDto,
  IncidentStatus,
  UserDto,
} from "../src/contracts";
import { LocaleProvider } from "../src/i18n/LocaleContext";
import { IncidentDetailPage } from "../src/pages/IncidentDetailPage";

const TIMESTAMP = "2026-07-15T03:00:00Z";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("Incident status recovery", () => {
  it("allows ADMIN to reopen a CLOSED Incident and keeps its evidence visible", async () => {
    const update = arrangeApi();
    renderDetail("ADMIN");

    expect(await screen.findByRole("heading", { name: "Credential access investigation" })).toBeInTheDocument();
    expect(screen.getByText("No connected Alerts")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "OPEN" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Incident status" }));

    await waitFor(() => expect(update).toHaveBeenCalledWith(21, { status: "OPEN" }));
    expect(await screen.findByText("Incident status saved.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Credential access investigation" })).toBeInTheDocument();
  });

  it("keeps Incident status controls hidden for VIEWER", async () => {
    arrangeApi();
    renderDetail("VIEWER");

    expect(await screen.findByRole("heading", { name: "Credential access investigation" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save Incident status" })).not.toBeInTheDocument();
    expect(screen.getByText("VIEWER can inspect the current status but cannot change it.")).toBeInTheDocument();
  });
});

function arrangeApi() {
  let status: IncidentStatus = "CLOSED";
  let updatedAt = TIMESTAMP;
  vi.spyOn(api, "incident").mockImplementation(async () => envelope(detail(status, updatedAt)));
  vi.spyOn(api, "incidents").mockImplementation(async (query) => {
    const items = !query.status || query.status === status ? [summary(status, updatedAt)] : [];
    return envelope({ items, page: 1, size: 500, total: items.length, totalPages: items.length ? 1 : 0 });
  });
  vi.spyOn(api, "incidentTimeline").mockResolvedValue(envelope<AttackTimelineDto>({
    incidentId: 21,
    endpointId: 1001,
    items: [],
  }));
  vi.spyOn(api, "incidentInvestigation").mockResolvedValue(envelope<IncidentInvestigationDto>({
    incidentId: 21,
    timeRange: { from: "2026-07-15T02:00:00Z", to: "2026-07-15T04:00:00Z" },
    nodes: [],
    edges: [],
    nodeCount: 0,
    edgeCount: 0,
    truncated: false,
    partial: false,
    warnings: [],
    fallback: { timelineAvailable: true, alertTableAvailable: true, eventTableAvailable: true },
  }));
  return vi.spyOn(api, "updateIncident").mockImplementation(async (incidentId, body) => {
    status = body.status;
    updatedAt = "2026-07-15T03:05:00Z";
    return envelope({ ...summary(status, updatedAt), incidentId });
  });
}

function renderDetail(role: UserDto["role"]) {
  sessionStorage.setItem("edr.authSession", JSON.stringify({
    token: "incident-status-token",
    user: { userId: 1, loginId: "operator", name: "Operator", role, status: "ACTIVE", locale: "EN" },
    expiresAt: Date.now() + 60_000,
  }));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <LocaleProvider>
          <MemoryRouter initialEntries={["/incidents/21?status=CLOSED"]}>
            <Routes><Route path="/incidents/:incidentId" element={<IncidentDetailPage />} /></Routes>
          </MemoryRouter>
        </LocaleProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function detail(status: IncidentStatus, updatedAt: string): IncidentDetailDto {
  return { ...summary(status, updatedAt), alerts: [] };
}

function summary(status: IncidentStatus, updatedAt: string): IncidentDto {
  return {
    incidentId: 21,
    endpointId: 1001,
    correlationKey: "endpoint:1001:credential-access",
    windowStartAt: "2026-07-15T02:00:00Z",
    windowEndAt: "2026-07-15T03:00:00Z",
    title: "Credential access investigation",
    description: "Correlated credential access evidence",
    severity: "CRITICAL",
    status,
    firstDetectedAt: "2026-07-15T02:00:00Z",
    lastDetectedAt: "2026-07-15T02:30:00Z",
    closedAt: status === "CLOSED" ? "2026-07-15T03:00:00Z" : null,
    createdAt: "2026-07-15T02:00:00Z",
    updatedAt,
    alertCount: 0,
  };
}

function envelope<Data>(data: Data) {
  return { data, meta: { requestId: "req_incident_status" } };
}
