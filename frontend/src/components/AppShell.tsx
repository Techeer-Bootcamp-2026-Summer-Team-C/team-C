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
import type { UserLocale } from "../contracts";
import { useI18n } from "../i18n/LocaleContext";

const NAVIGATION = [
  { to: "/", labelKey: "navigation.overview", icon: MonitorDot, end: true },
  { to: "/alerts", labelKey: "navigation.alerts", icon: BellRing, end: false },
  { to: "/incidents", labelKey: "navigation.incidents", icon: ShieldCheck, end: false },
  { to: "/endpoints", labelKey: "navigation.endpoints", icon: Server, end: false },
  { to: "/events", labelKey: "navigation.events", icon: Activity, end: false },
  { to: "/operations", labelKey: "navigation.operations", icon: Database, end: false },
] as const;

const COMPACT_KEY = "edr.compactNavigation";

export function AppShell() {
  const auth = useAuth();
  const { locale, t } = useI18n();
  const location = useLocation();
  const [compact, setCompact] = useState(() => localStorage.getItem(COMPACT_KEY) !== "false");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [localeSaving, setLocaleSaving] = useState(false);
  const [localeError, setLocaleError] = useState(false);
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

  return (
    <div className={compact ? "app-shell compact" : "app-shell"}>
      <a className="skip-link" href="#main-content">{t("navigation.skipToContent")}</a>
      <aside className={mobileOpen ? "nav-rail mobile-open" : "nav-rail"}>
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
              onClick={() => setMobileOpen(false)}
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
            aria-expanded={mobileOpen}
            aria-label={t("navigation.toggle")}
            className="mobile-menu"
            onClick={() => setMobileOpen((current) => !current)}
            type="button"
          >
            <Menu aria-hidden="true" size={20} />
          </button>
          <div className="top-title">
            <span>EDR / OPERATIONS</span>
            <strong>{pageTitleText}</strong>
          </div>
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
      </section>
    </div>
  );
}
