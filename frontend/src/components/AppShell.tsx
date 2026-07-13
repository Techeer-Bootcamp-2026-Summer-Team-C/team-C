import {
  Activity,
  BellRing,
  Database,
  LogOut,
  Menu,
  MonitorDot,
  Radar,
  PanelLeftClose,
  PanelLeftOpen,
  Printer,
  Search,
  Server,
  ShieldCheck,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const NAVIGATION = [
  { to: "/", label: "Overview", icon: MonitorDot, end: true },
  { to: "/alerts", label: "Alerts", icon: BellRing, end: false },
  { to: "/incidents", label: "Incidents", icon: ShieldCheck, end: false },
  { to: "/endpoints", label: "Endpoints", icon: Server, end: false },
  { to: "/events", label: "Events", icon: Activity, end: false },
  { to: "/intelligence", label: "Intelligence", icon: Radar, end: false },
  { to: "/operations", label: "Operations", icon: Database, end: false },
] as const;

const COMPACT_KEY = "edr.compactNavigation";

export function AppShell() {
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [compact, setCompact] = useState(() => localStorage.getItem(COMPACT_KEY) !== "false");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [reportOpen, setReportOpen] = useState(false);
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

  function submitSearch(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const value = search.trim();
    if (!value) return;
    const query = new URLSearchParams();
    if (/^[1-9]\d*$/.test(value)) query.set("endpointId", value);
    else query.set("processName", value);
    navigate(`/events?${query.toString()}`);
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
          <form className="global-search" onSubmit={submitSearch} role="search">
            <Search aria-hidden="true" size={16} />
            <input aria-label="Search Event evidence" onChange={(event) => setSearch(event.target.value)} placeholder="Endpoint ID or process" value={search} />
          </form>
          <div className="session-summary">
            <button aria-label="Open printable report" className="icon-button" onClick={() => setReportOpen(true)} title="Print report" type="button"><Printer aria-hidden="true" size={18} /></button>
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
        {reportOpen ? <div className="modal-backdrop" role="presentation" onMouseDown={() => setReportOpen(false)}><section aria-labelledby="report-title" aria-modal="true" className="report-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
          <span className="eyebrow">BROWSER REPORT</span><h2 id="report-title">{pageTitle} snapshot</h2>
          <p>Print the currently visible dashboard state or save it as PDF using the browser print dialog. Applied filters and read-only evidence remain visible in the print layout.</p>
          <dl><div><dt>Page</dt><dd>{location.pathname}</dd></div><div><dt>Generated</dt><dd>{new Date().toLocaleString()}</dd></div><div><dt>User role</dt><dd>{auth.user?.role}</dd></div></dl>
          <div className="modal-actions"><button className="button ghost" onClick={() => setReportOpen(false)} type="button">Cancel</button><button className="button" onClick={() => window.print()} type="button"><Printer aria-hidden="true" size={16} />Print / Save PDF</button></div>
        </section></div> : null}
      </section>
    </div>
  );
}
