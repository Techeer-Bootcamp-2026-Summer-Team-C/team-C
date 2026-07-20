import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, RequireAuth } from "../src/auth/AuthContext";
import { AppShell } from "../src/components/AppShell";
import { LocaleProvider } from "../src/i18n/LocaleContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";

const USER = { userId: 1, loginId: "admin", name: "Administrator", role: "ADMIN", status: "ACTIVE", locale: "EN" } as const;

beforeEach(() => {
  sessionStorage.setItem("edr.authSession", JSON.stringify({ token: "shell-token", user: USER, expiresAt: Date.now() + 60_000 }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(success(USER)));
});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("application shell foundation", () => {
  it("shows the service name instead of duplicate Overview breadcrumbs on the root route", async () => {
    renderRootShell();
    expect(await screen.findByRole("heading", { name: "Overview destination" })).toBeInTheDocument();
    expect(screen.getAllByLabelText("EDR Console")).not.toHaveLength(0);
    expect(screen.getByText("EDR Console", { selector: ".top-title > strong" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Breadcrumb" })).not.toBeInTheDocument();
  });

  it("renders approved navigation groups, child hierarchy, and route breadcrumbs", async () => {
    renderShell();
    expect(await screen.findByRole("heading", { name: "Archive destination" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Overview" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Triage" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evidence" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Analysis" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Platform" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Dashboards" })).not.toBeInTheDocument();
    expect(screen.queryByText("Endpoint Defense")).not.toBeInTheDocument();
    expect(screen.queryByText("EDR / SOC")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Investigation path")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Archives" })).toHaveClass("nav-child", "active");

    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByRole("link", { name: "Operations" })).toHaveAttribute("href", "/operations");
    expect(within(breadcrumb).getByText("Archives")).toHaveAttribute("aria-current", "page");

    await userEvent.click(screen.getByRole("button", { name: "Compact navigation" }));
    expect(screen.getByRole("button", { name: "Expand navigation" })).toBeInTheDocument();
  });

  it("keeps the dashboard workbench out of primary navigation while exposing its route breadcrumb", async () => {
    renderDashboardShell();
    expect(await screen.findByRole("heading", { name: "Dashboard workbench destination" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Dashboards" })).not.toBeInTheDocument();
    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByText("Dashboards")).toHaveAttribute("aria-current", "page");
  });

  it("carries the current time scope between time-aware primary routes", async () => {
    const user = userEvent.setup();
    renderTimeScopeShell();
    expect(await screen.findByTestId("location")).toHaveTextContent("/alerts?timePreset=LATEST_7D");
    expect(screen.getByRole("link", { name: "Incidents" })).toHaveAttribute("href", "/incidents?timePreset=LATEST_7D");
    expect(screen.getByRole("link", { name: "Archives" })).toHaveAttribute("href", "/operations/archives");

    await user.click(screen.getByRole("link", { name: "Endpoints" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/endpoints");
    await waitFor(() => expect(screen.getByRole("link", { name: "Events" })).toHaveAttribute("href", "/events?timePreset=LATEST_7D"));
  });

  it("operates the mobile Drawer and account/report surfaces by keyboard", async () => {
    const user = userEvent.setup();
    renderShell();
    await screen.findByRole("heading", { name: "Archive destination" });

    const menuTrigger = screen.getByRole("button", { name: "Toggle navigation" });
    await user.click(menuTrigger);
    expect(screen.getByRole("dialog", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close navigation" })).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(menuTrigger).toHaveFocus());

    const accountTrigger = screen.getByRole("button", { name: "Open account menu" });
    await user.click(accountTrigger);
    expect(screen.getByRole("dialog", { name: "Open account menu" })).toHaveTextContent("Administrator");
    expect(screen.getByText("ADMIN")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open printable report" }));
    expect(screen.getByRole("dialog", { name: "Archives snapshot" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close report" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Archives snapshot" })).not.toBeInTheDocument();
  });

  it("switches the Case 2 shell between dark and light themes", async () => {
    renderRootShell();
    await screen.findByRole("heading", { name: "Overview destination" });
    expect(document.documentElement).not.toHaveClass("light");
    expect(localStorage.getItem("edr.theme")).toBeNull();
    const toggle = screen.getByRole("button", { name: "Switch to light theme" });
    await userEvent.click(toggle);
    expect(document.documentElement).toHaveClass("light");
    expect(localStorage.getItem("edr.theme")).toBe("light");
    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
  });

  it("keeps the authenticated shell usable when the localStorage getter throws", async () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, "localStorage");
    expect(descriptor).toBeDefined();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get: () => { throw new DOMException("blocked", "SecurityError"); },
    });

    try {
      const user = userEvent.setup();
      const view = renderRootShell();
      expect(await screen.findByRole("heading", { name: "Overview destination" })).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Compact navigation" }));
      expect(screen.getByRole("button", { name: "Expand navigation" })).toBeInTheDocument();
      view.unmount();
    } finally {
      if (descriptor) Object.defineProperty(window, "localStorage", descriptor);
    }
  });
});

function renderShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <LocaleProvider>
            <MemoryRouter initialEntries={["/operations/archives"]}>
              <Routes>
                <Route element={<RequireAuth><AppShell /></RequireAuth>}>
                  <Route path="operations">
                    <Route index element={<h1>Operations destination</h1>} />
                    <Route path="archives" element={<h1>Archive destination</h1>} />
                  </Route>
                </Route>
              </Routes>
            </MemoryRouter>
          </LocaleProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function renderRootShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <LocaleProvider>
            <MemoryRouter initialEntries={["/"]}>
              <Routes>
                <Route element={<RequireAuth><AppShell /></RequireAuth>}>
                  <Route index element={<h1>Overview destination</h1>} />
                </Route>
              </Routes>
            </MemoryRouter>
          </LocaleProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function renderDashboardShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <LocaleProvider>
            <MemoryRouter initialEntries={["/dashboards"]}>
              <Routes>
                <Route element={<RequireAuth><AppShell /></RequireAuth>}>
                  <Route path="dashboards" element={<h1>Dashboard workbench destination</h1>} />
                </Route>
              </Routes>
            </MemoryRouter>
          </LocaleProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function renderTimeScopeShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <LocaleProvider>
            <MemoryRouter initialEntries={["/alerts?timePreset=LATEST_7D"]}>
              <Routes>
                <Route element={<RequireAuth><AppShell /></RequireAuth>}>
                  <Route path="*" element={<LocationProbe />} />
                </Route>
              </Routes>
            </MemoryRouter>
          </LocaleProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

function success(data: unknown): Response {
  return new Response(JSON.stringify({ data, meta: { requestId: "req_shell" } }), { status: 200, headers: { "Content-Type": "application/json" } });
}
