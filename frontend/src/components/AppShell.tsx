import {
  Activity,
  BellRing,
  Database,
  LogOut,
  Menu,
  MonitorDot,
  PanelLeftClose,
  PanelLeftOpen,
  Server,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const NAVIGATION = [
  { to: "/", label: "Overview", icon: MonitorDot, end: true },
  { to: "/alerts", label: "Alerts", icon: BellRing, end: false },
  { to: "/incidents", label: "Incidents", icon: ShieldCheck, end: false },
  { to: "/endpoints", label: "Endpoints", icon: Server, end: false },
  { to: "/events", label: "Events", icon: Activity, end: false },
  { to: "/operations", label: "Operations", icon: Database, end: false },
] as const;

const COMPACT_KEY = "edr.compactNavigation";

export function AppShell() {
  const auth = useAuth();
  const location = useLocation();
  const [compact, setCompact] = useState(() => localStorage.getItem(COMPACT_KEY) !== "false");
  const [mobileOpen, setMobileOpen] = useState(false);
  const pageTitle = NAVIGATION.find((item) =>
    item.end ? location.pathname === item.to : location.pathname.startsWith(item.to),
  )?.label ?? "EDR Console";

  function toggleCompact(): void {
    setCompact((current) => {
      const next = !current;
      localStorage.setItem(COMPACT_KEY, String(next));
      return next;
    });
  }

  function logOut(): void {
    auth.logout();
  }

  return (
    <div className={compact ? "app-shell compact" : "app-shell"}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className={mobileOpen ? "nav-rail mobile-open" : "nav-rail"}>
        <div className="brand-mark" aria-label="EDR Console">EC</div>
        <nav aria-label="Primary navigation">
          {NAVIGATION.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              aria-label={label}
              className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
              end={end}
              key={to}
              onClick={() => setMobileOpen(false)}
              title={label}
              to={to}
            >
              <Icon aria-hidden="true" size={19} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <button className="nav-compact" onClick={toggleCompact} type="button">
          {compact ? <PanelLeftOpen aria-hidden="true" size={18} /> : <PanelLeftClose aria-hidden="true" size={18} />}
          <span>{compact ? "Expand navigation" : "Compact navigation"}</span>
        </button>
      </aside>
      <section className="console-shell">
        <header className="top-bar">
          <button
            aria-expanded={mobileOpen}
            aria-label="Toggle navigation"
            className="mobile-menu"
            onClick={() => setMobileOpen((current) => !current)}
            type="button"
          >
            <Menu aria-hidden="true" size={20} />
          </button>
          <div className="top-title">
            <span>EDR / OPERATIONS</span>
            <strong>{pageTitle}</strong>
          </div>
          <div className="session-summary">
            <span className="role-label">{auth.user?.role}</span>
            <span>{auth.user?.name}</span>
            <button aria-label="Log out" className="icon-button" onClick={logOut} title="Log out" type="button">
              <LogOut aria-hidden="true" size={18} />
            </button>
          </div>
        </header>
        <main className="main-content" id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
      </section>
    </div>
  );
}
