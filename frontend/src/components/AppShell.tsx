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
import type { UserLocale } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";

const NAVIGATION = [
  { to: "/", labelKey: "navigation.overview", icon: MonitorDot, end: true },
  { to: "/alerts", labelKey: "navigation.alerts", icon: BellRing, end: false },
  { to: "/incidents", labelKey: "navigation.incidents", icon: ShieldCheck, end: false },
  { to: "/endpoints", labelKey: "navigation.endpoints", icon: Server, end: false },
  { to: "/events", labelKey: "navigation.events", icon: Activity, end: false },
  { to: "/intelligence", labelKey: "navigation.intelligence", icon: Radar, end: false },
  { to: "/operations", labelKey: "navigation.operations", icon: Database, end: false },
] as const;

const COMPACT_KEY = "edr.compactNavigation";

export function AppShell() {
  const auth = useAuth();
  const { dateLocale, locale, t } = useI18n();
  const location = useLocation();
  const navigate = useNavigate();
  const [compact, setCompact] = useState(() => localStorage.getItem(COMPACT_KEY) !== "false");
  const [compactNavOpen, setCompactNavOpen] = useState(false);
  const [localeSaving, setLocaleSaving] = useState(false);
  const [localeError, setLocaleError] = useState(false);
  const [search, setSearch] = useState("");
  const [reportOpen, setReportOpen] = useState(false);
  const pageTitle = NAVIGATION.find((item) =>
    item.end ? location.pathname === item.to : location.pathname.startsWith(item.to),
  );
  const pageTitleText = pageTitle ? t(pageTitle.labelKey) : t("navigation.console");

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

  async function changeLocale(nextLocale: UserLocale): Promise<void> {
    if (nextLocale === locale || localeSaving) return;
    setLocaleSaving(true);
    setLocaleError(false);
    try {
      await auth.updateLocale(nextLocale);
    } catch {
      setLocaleError(true);
    } finally {
      setLocaleSaving(false);
    }
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
      <a className="skip-link" href="#main-content">{t("navigation.skipToContent")}</a>
      <aside className={compactNavOpen ? "nav-rail compact-nav-open" : "nav-rail"}>
        <div className="brand-mark" aria-label="EDR Console">EC</div>
        <nav aria-label={t("navigation.primary")}>
          {NAVIGATION.map(({ to, labelKey, icon: Icon, end }) => {
            const label = t(labelKey);
            return (
            <NavLink
              aria-label={label}
              className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
              end={end}
              key={to}
              onClick={() => setCompactNavOpen(false)}
              title={label}
              to={to}
            >
              <Icon aria-hidden="true" size={19} />
              <span>{label}</span>
            </NavLink>
            );
          })}
        </nav>
        <button className="nav-compact" onClick={toggleCompact} type="button">
          {compact ? <PanelLeftOpen aria-hidden="true" size={18} /> : <PanelLeftClose aria-hidden="true" size={18} />}
          <span>{compact ? t("navigation.expand") : t("navigation.compact")}</span>
        </button>
      </aside>
      <section className="console-shell">
        <header className="top-bar">
          <button
            aria-expanded={compactNavOpen}
            aria-label={t("navigation.toggle")}
            className="compact-nav-menu"
            onClick={() => setCompactNavOpen((current) => !current)}
            type="button"
          >
            <Menu aria-hidden="true" size={20} />
          </button>
          <div className="top-title">
            <span>EDR / OPERATIONS</span>
            <strong>{pageTitleText}</strong>
          </div>
          <form className="global-search" onSubmit={submitSearch} role="search">
            <Search aria-hidden="true" size={16} />
            <input aria-label={t("search.aria")} onChange={(event) => setSearch(event.target.value)} placeholder={t("search.placeholder")} value={search} />
          </form>
          <div className="session-summary">
            <div className="locale-control">
              <label className="locale-selector">
                <span>{t("language.label")}</span>
                <select
                  aria-label={t("language.label")}
                  disabled={localeSaving}
                  onChange={(event) => void changeLocale(event.target.value as UserLocale)}
                  value={locale}
                >
                  <option value="EN">{t("language.english")}</option>
                  <option value="KO">{t("language.korean")}</option>
                </select>
              </label>
              {localeError ? <span className="locale-error" role="alert">{t("language.saveError")}</span> : null}
            </div>
            <button aria-label={t("report.openAria")} className="icon-button" onClick={() => setReportOpen(true)} title={t("report.printTitle")} type="button"><Printer aria-hidden="true" size={18} /></button>
            <span className="role-label">{auth.user?.role}</span>
            <span>{auth.user?.name}</span>
            <button aria-label={t("navigation.logout")} className="icon-button" onClick={logOut} title={t("navigation.logout")} type="button">
              <LogOut aria-hidden="true" size={18} />
            </button>
          </div>
        </header>
        <main className="main-content" id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
        {reportOpen ? <div className="modal-backdrop" role="presentation" onMouseDown={() => setReportOpen(false)}><section aria-labelledby="report-title" aria-modal="true" className="report-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
          <span className="eyebrow">BROWSER REPORT</span><h2 id="report-title">{t("report.snapshot", { page: pageTitleText })}</h2>
          <p>{t("report.description")}</p>
          <dl><div><dt>{t("report.page")}</dt><dd>{location.pathname}</dd></div><div><dt>{t("report.generated")}</dt><dd>{new Date().toLocaleString(dateLocale)}</dd></div><div><dt>{t("report.userRole")}</dt><dd>{auth.user?.role}</dd></div></dl>
          <div className="modal-actions"><button className="button ghost" onClick={() => setReportOpen(false)} type="button">{t("report.cancel")}</button><button className="button" onClick={() => window.print()} type="button"><Printer aria-hidden="true" size={16} />{t("report.printSave")}</button></div>
        </section></div> : null}
      </section>
    </div>
  );
}
