import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, RequireAuth } from "../src/auth/AuthContext";
import { AppShell } from "../src/components/AppShell";
import { TimeSeriesChart } from "../src/components/charts";
import type { AttackTimelineDto } from "../src/contracts";
import { LocaleProvider, useI18n } from "../src/i18n/LocaleContext";
import {
  detectionRuleName,
  detectionSummary,
  detectionTitle,
  responseGuidanceTitle,
  riskFactorDescription,
} from "../src/i18n/detectionCopy";
import { translate } from "../src/i18n/translations";
import { formatDateTime } from "../src/lib/format";
import { LoginPage } from "../src/pages/LoginPage";
import { AttackTimeline } from "../src/pages/IncidentDetailPage";
import { operationsDetail } from "../src/pages/OperationsPage";
import { ThemeProvider } from "../src/theme/ThemeProvider";

const EN_USER = { userId: 1, loginId: "analyst", name: "Analyst", role: "ANALYST", status: "ACTIVE", locale: "EN" } as const;
const KO_USER = { ...EN_USER, locale: "KO" } as const;

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
  document.documentElement.classList.remove("light");
  document.documentElement.lang = "en";
  vi.unstubAllGlobals();
});

describe("authenticated locale lifecycle", () => {
  it("normalizes a legacy session to EN, then resynchronizes the Backend KO locale without changing the route", async () => {
    storeSession({ ...EN_USER, locale: undefined });
    let resolveMe: ((response: Response) => void) | undefined;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith("/users/me")) {
        return new Promise<Response>((resolve) => { resolveMe = resolve; });
      }
      return Promise.reject(new Error("Unexpected request"));
    }));

    renderShell();
    expect(screen.getByRole("combobox", { name: "Language" })).toHaveValue("EN");
    expect(sessionStorage.getItem("edr.authSession")).toContain('"locale":"EN"');

    await act(async () => { resolveMe?.(success(KO_USER)); });
    expect(await screen.findByText("본문 바로가기")).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/alerts?status=OPEN");
    expect(document.documentElement.lang).toBe("ko");
    expect(sessionStorage.getItem("edr.authSession")).toContain('"locale":"KO"');
  });

  it("saves KO once, updates the whole shell and session immediately, and formats dates with ko-KR", async () => {
    storeSession(EN_USER);
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/users/me/locale")) return Promise.resolve(success(KO_USER));
      if (path.endsWith("/users/me")) return Promise.resolve(success(EN_USER));
      return Promise.reject(new Error(`Unexpected request: ${path} ${init?.method ?? "GET"}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderShell();
    const selector = await screen.findByRole("combobox", { name: "Language" });
    fireEvent.change(selector, { target: { value: "EN" } });
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/users/me/locale"))).toHaveLength(0);
    await userEvent.selectOptions(selector, "KO");

    expect(await screen.findByRole("combobox", { name: "언어" })).toHaveValue("KO");
    expect(screen.getByText("본문 바로가기")).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/alerts?status=OPEN");
    expect(sessionStorage.getItem("edr.authSession")).toContain('"locale":"KO"');
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/users/me/locale"))).toHaveLength(1);
    expect(screen.getByTestId("date")).toHaveTextContent(expectedDate("ko-KR"));
  });

  it("keeps the previous locale and exposes an accessible error when PATCH fails", async () => {
    storeSession(EN_USER);
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/users/me/locale")) return Promise.resolve(failure(503, "SERVICE_UNAVAILABLE"));
      if (path.endsWith("/users/me")) return Promise.resolve(success(EN_USER));
      return Promise.reject(new Error("Unexpected request"));
    }));

    renderShell();
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Language" }), "KO");
    expect(await screen.findByRole("alert")).toHaveTextContent("Language preference could not be saved");
    expect(screen.getByRole("combobox", { name: "Language" })).toHaveValue("EN");
    expect(sessionStorage.getItem("edr.authSession")).toContain('"locale":"EN"');
    expect(document.documentElement.lang).toBe("en");
  });

  it("keeps a restored KO session during a temporary /users/me failure without a live-region error", async () => {
    storeSession(KO_USER);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(failure(503, "SERVICE_UNAVAILABLE")));
    renderShell();
    expect(await screen.findByRole("combobox", { name: "언어" })).toHaveValue("KO");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(sessionStorage.getItem("edr.authSession")).toContain('"locale":"KO"');
  });

  it("keeps LoginPage English, applies login KO after authentication, and resets to English on logout", async () => {
    localStorage.setItem("edr.theme", "light");
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/auth/login")) {
        return Promise.resolve(success({ accessToken: "locale-token", tokenType: "Bearer", expiresIn: 43_200, user: KO_USER }));
      }
      if (path.endsWith("/users/me")) return Promise.resolve(success(KO_USER));
      return Promise.reject(new Error("Unexpected request"));
    }));

    renderShell("/login");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText("OWLBY / SINGLE TENANT")).toBeInTheDocument();
    expect(document.documentElement).toHaveClass("light");
    await userEvent.type(screen.getByLabelText("Login ID"), "analyst");
    await userEvent.type(screen.getByLabelText("Password"), "password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("button", { name: "계정 메뉴 열기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다크 테마로 전환" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("ko");

    await userEvent.click(screen.getByRole("button", { name: "계정 메뉴 열기" }));
    await userEvent.click(screen.getByRole("button", { name: "로그아웃" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText("Move from signal to evidence.")).toBeInTheDocument();
    expect(document.documentElement).toHaveClass("light");
    await waitFor(() => expect(document.documentElement.lang).toBe("en"));
  });

  it("does not restore a logged-out session when a locale PATCH finishes late", async () => {
    storeSession(EN_USER);
    let resolveLocale: ((response: Response) => void) | undefined;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/users/me/locale")) {
        return new Promise<Response>((resolve) => { resolveLocale = resolve; });
      }
      if (path.endsWith("/users/me")) return Promise.resolve(success(EN_USER));
      return Promise.reject(new Error("Unexpected request"));
    }));

    renderShell();
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Language" }), "KO");
    expect(screen.getByRole("combobox", { name: "Language" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Open account menu" }));
    await userEvent.click(screen.getByRole("button", { name: "Log out" }));
    expect(sessionStorage.getItem("edr.authSession")).toBeNull();

    await act(async () => { resolveLocale?.(success(KO_USER)); });
    await waitFor(() => expect(sessionStorage.getItem("edr.authSession")).toBeNull());
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
  });
});

it("preserves the English regression copy and uses the agreed mixed Korean terminology", () => {
  expect(translate("EN", "overview.eyebrow")).toBe("CURRENT POSTURE");
  expect(translate("EN", "overview.topRules")).toBe("Top rules");
  expect(translate("EN", "edrState.calculated", { time: "now" })).toBe("Calculated now");
  expect(translate("KO", "overview.topRules")).toBe("탐지 빈도 상위 Rule");
  expect(translate("KO", "incident.eyebrow")).toBe("ALERT CORRELATION");
  expect(translate("KO", "edrState.current")).toBe("현재 EDR 상태");
  expect(translate("KO", "edrState.noReasons")).toBe("활성 Risk 요인 없음");
  expect(translate("KO", "alert.responseGuidance")).toBe("Response 가이던스");
  expect(translate("KO", "event.rawPayload")).toBe("원본 Payload");
  expect(translate("KO", "event.processTree")).toBe("Process Tree");
  expect(translate("KO", "operations.failureQueue")).toBe("Failure Queue");
  expect(translate("KO", "intelligence.mitreTactics")).toBe("MITRE Tactic");
});

it("localizes known Backend detection copy without changing unknown values", () => {
  const ko = (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) => translate("KO", key, params);
  expect(detectionTitle(ko, "Encoded PowerShell command detected", "PROC_POWERSHELL_ENCODED")).toBe("인코딩된 PowerShell 명령 실행 탐지");
  expect(detectionSummary(ko, "PowerShell was executed with an encoded command argument.", "")).toBe("인코딩된 명령 인자로 PowerShell이 실행되었습니다.");
  expect(detectionTitle(ko, "Rare Domain Query on ENG-WIN-038")).toBe(translate("KO", "detection.dnsRareDomain.titleOnEndpoint", { endpoint: "ENG-WIN-038" }));
  expect(detectionTitle(ko, "Unusual HTTPS Upload", "L7_UPLOAD_ANOMALY")).toBe(translate("KO", "detection.l7UploadAnomaly.ruleName"));
  expect(detectionRuleName(ko, "Suspicious File Drop", "FILE_SUSPICIOUS_DROP")).toBe(translate("KO", "detection.fileSuspiciousDrop.ruleName"));
  expect(detectionSummary(ko, "A process created a suspicious payload or artifact file.", "")).toBe(translate("KO", "detection.fileSuspiciousDrop.summary"));
  expect(detectionSummary(ko, "Deterministic long-range QA alert for ENG-WIN-038.", "")).toBe(translate("KO", "detection.qaLongRange.summary", { agentId: "ENG-WIN-038" }));
  expect(responseGuidanceTitle(ko, "Block confirmed malicious domain")).toBe(translate("KO", "guidance.blockMaliciousDomain"));
  expect(riskFactorDescription(ko, "OPEN correlation Incident contribution")).toBe(translate("KO", "risk.openIncidentContribution"));
  expect(detectionTitle(ko, "Unknown detector")).toBe("Unknown detector");
  expect(detectionRuleName(ko, "Unknown rule")).toBe("Unknown rule");
  expect(responseGuidanceTitle(ko, "Unknown response")).toBe("Unknown response");
  expect(riskFactorDescription(ko, "Unknown factor")).toBe("Unknown factor");
});

it("localizes known Operations Backend detail sentences without rewriting unknown evidence", () => {
  const ko = (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) => translate("KO", key, params);
  expect(operationsDetail(ko, "The authenticated operations endpoint is responding.")).toBe(translate("KO", "operations.backendResponding"));
  expect(operationsDetail(ko, "Live dependency probe succeeded.")).toBe(translate("KO", "operations.liveProbeSucceeded"));
  expect(operationsDetail(ko, "Live dependency probe failed.")).toBe(translate("KO", "operations.liveProbeFailedPlain"));
  expect(operationsDetail(ko, "Worker probe failed.")).toBe(translate("KO", "operations.workerProbeFailedPlain"));
  expect(operationsDetail(ko, "Broker group state: Stable")).toBe(translate("KO", "operations.brokerGroupState", { state: "Stable" }));
  expect(operationsDetail(ko, "Unknown operational evidence")).toBe("Unknown operational evidence");
});

it("localizes Alert timeline copy even when the Alert carries a source Event ID", async () => {
  storeSession(KO_USER);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(success(KO_USER)));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const timeline: AttackTimelineDto = {
    incidentId: 1,
    endpointId: 1,
    items: [{
      itemType: "ALERT",
      occurredAt: "2026-07-16T13:51:14Z",
      title: "Encoded PowerShell command detected",
      summary: "PowerShell was executed with an encoded command argument.",
      severity: "HIGH",
      eventType: "PROCESS_EXECUTION",
      eventId: "source-event-1",
      alertId: 11,
      incidentId: 1,
      endpointId: 1,
    }],
  };

  render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <LocaleProvider>
            <MemoryRouter>
              <AttackTimeline investigation={null} onSelect={() => undefined} selection={null} timeline={timeline} />
            </MemoryRouter>
          </LocaleProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );

  expect(await screen.findByText(translate("KO", "detection.procPowershellEncoded.title"))).toBeInTheDocument();
  expect(screen.getByText(translate("KO", "detection.procPowershellEncoded.summary"))).toBeInTheDocument();
  expect(screen.queryByText("PowerShell was executed with an encoded command argument.")).not.toBeInTheDocument();
});

it("preserves Event capitalization in Korean time-series copy", async () => {
  storeSession(KO_USER);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(success(KO_USER)));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <LocaleProvider>
            <TimeSeriesChart label="Event" rows={[]} />
            <TimeSeriesChart label="Event" rows={[{ bucketStartAt: "2026-07-15T03:00:00Z", count: 1 }]} />
          </LocaleProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );

  expect(await screen.findByText("Event 시계열이 없습니다")).toBeInTheDocument();
  expect(screen.getByText("Event 데이터 표 보기")).toBeInTheDocument();
});

function renderShell(initialEntry = "/alerts?status=OPEN") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <LocaleProvider>
            <MemoryRouter initialEntries={[initialEntry]}>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route element={<RequireAuth><AppShell /></RequireAuth>}>
                  <Route index element={<LocaleProbe />} />
                  <Route path="alerts" element={<LocaleProbe />} />
                </Route>
              </Routes>
            </MemoryRouter>
          </LocaleProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function LocaleProbe() {
  useI18n();
  const location = useLocation();
  return <><output data-testid="location">{location.pathname}{location.search}</output><time data-testid="date">{formatDateTime("2026-07-15T03:00:00Z")}</time></>;
}

function storeSession(user: Record<string, unknown>): void {
  sessionStorage.setItem("edr.authSession", JSON.stringify({ token: "stored-token", user, expiresAt: Date.now() + 60_000 }));
}

function success(data: unknown): Response {
  return new Response(JSON.stringify({ data, meta: { requestId: "req_locale" } }), { status: 200, headers: { "Content-Type": "application/json" } });
}

function failure(status: number, code: string): Response {
  return new Response(JSON.stringify({ error: { code, message: "Backend message", retryable: status >= 500, details: [] }, meta: { requestId: "req_locale_error" } }), { status, headers: { "Content-Type": "application/json" } });
}

function expectedDate(locale: "en-US" | "ko-KR"): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "medium" }).format(new Date("2026-07-15T03:00:00Z"));
}
