import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../src/auth/AuthContext";
import { EndpointSwitcher } from "../src/components/EndpointSwitcher";
import { RawPayloadViewer } from "../src/components/RawPayloadViewer";
import type { EventDetailDto } from "../src/contracts";
import { eventDetailGroups, eventListSummary } from "../src/features/eventPresentation";
import { LocaleProvider } from "../src/i18n/LocaleContext";
import { CertificateCard } from "../src/pages/EndpointDetailPage";
import { eventFixture } from "./contracts.fixture";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Endpoint switcher and Event evidence", () => {
  it("does not prefetch the fleet and uses paged server search with keyboard navigation", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(success({ items: [endpointRow], page: 1, size: 20, total: 1 })), { status: 200, headers: { "Content-Type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<><EndpointSwitcher currentEndpointId={1001} params={new URLSearchParams("status=OFFLINE&page=3&selected=1001")} /><LocationProbe /></>, "/endpoints/1001?status=OFFLINE&page=3&selected=1001");
    expect(fetchMock).not.toHaveBeenCalled();
    const input = screen.getByRole("combobox", { name: "Switch Endpoint" });
    await userEvent.type(input, "WIN-02");
    const option = await screen.findByRole("option", { name: /WIN-ENDPOINT-02/ });
    expect(option).toBeInTheDocument();
    const requestUrl = String(fetchMock.mock.calls.at(-1)?.[0]);
    expect(requestUrl).toContain("q=WIN-02");
    expect(requestUrl).toContain("page=1");
    expect(requestUrl).toContain("size=20");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/endpoints/1002?status=OFFLINE&page=3&selected=1002"));
  });

  it("keeps Raw Payload collapsed, supports internal search, and copies exact JSON", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    renderWithProviders(<RawPayloadViewer payload={{ query: "example.com", nested: { answer: "example.com" } }} />);
    const details = screen.getByText("Raw payload").closest("details");
    expect(details).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Raw payload"));
    await userEvent.type(screen.getByRole("searchbox", { name: "Search Raw Payload" }), "example.com");
    expect(screen.getByText("2 matches")).toBeInTheDocument();
    expect(document.querySelectorAll("mark")).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Copy JSON" }));
    expect(writeText).toHaveBeenCalledWith(JSON.stringify({ query: "example.com", nested: { answer: "example.com" } }, null, 2));
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("selects only the field groups supported by each Event type fixture", () => {
    const base = eventFixture.data;
    const process = { ...base, eventType: "PROCESS_EXECUTION", processName: "powershell.exe", pid: 41 } satisfies EventDetailDto;
    const file = { ...base, eventType: "FILE_EVENT", filePath: "C:\\Temp\\sample.bin", fileAction: "CREATE" } satisfies EventDetailDto;
    const network = { ...base, eventType: "NETWORK_CONNECTION", remoteIp: "203.0.113.10", protocol: "TCP" } satisfies EventDetailDto;
    const dns = { ...base, eventType: "DNS_QUERY", dnsQuery: "example.com" } satisfies EventDetailDto;
    const l7 = { ...base, eventType: "L7_EVENT", httpMethod: "GET", httpHost: "example.com", tlsSni: "example.com" } satisfies EventDetailDto;
    expect(eventDetailGroups(process)).toEqual(["IDENTITY", "PROCESS", "DNS"]);
    expect(eventDetailGroups(file)).toContain("FILE");
    expect(eventDetailGroups(network)).toContain("NETWORK");
    expect(eventDetailGroups(dns)).toContain("DNS");
    expect(eventDetailGroups(l7)).toContain("HTTP_TLS");
    expect(eventListSummary(process)).toContain("powershell.exe");
  });

  it("visually and textually flags revoked or expired certificates", () => {
    renderWithProviders(<CertificateCard certificate={{ certFingerprint: "sha256:bad", certSubject: "CN=endpoint", certSanAgentId: "agent-2", issuedAt: "2026-01-01T00:00:00Z", expiresAt: "2026-02-01T00:00:00Z", isExpired: true, isRevoked: false, revokedAt: null }} />);
    const card = screen.getByRole("article", { name: /expired/i });
    expect(card).toHaveClass("anomalous");
    expect(screen.getByText("Certificate requires review")).toBeInTheDocument();
  });
});

function renderWithProviders(children: React.ReactNode, initialEntry = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><AuthProvider><LocaleProvider><MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter></LocaleProvider></AuthProvider></QueryClientProvider>);
}

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}{location.search}</span>;
}

function success(data: unknown) {
  return { data, meta: { requestId: "req_wp07" } };
}

const endpointRow = {
  endpointId: 1002,
  agentId: "agent-win-002",
  hostname: "WIN-ENDPOINT-02",
  osType: "WINDOWS",
  osVersion: "11",
  ipAddress: "10.0.0.2",
  agentVersion: "1.0.0",
  agentBuildId: "build-1",
  agentArch: "X86_64",
  capabilityCodes: [],
  status: "ONLINE",
  lastSeenAt: "2026-07-15T00:00:00Z",
  isStale: false,
  sensorHealth: [],
  risk: { score: 90, level: "CRITICAL", activeAlertCount: 2, openIncidentCount: 1, highestAlertRiskScore: 90, calculatedAt: "2026-07-15T00:00:00Z", riskFactors: [] },
  registeredAt: "2026-01-01T00:00:00Z",
};
