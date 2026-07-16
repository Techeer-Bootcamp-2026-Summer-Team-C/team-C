import {
  Activity,
  Archive,
  BellRing,
  CircleUserRound,
  Database,
  LogOut,
  Menu,
  MonitorDot,
  PanelLeftClose,
  PanelLeftOpen,
  Printer,
  Radar,
  Search,
  Server,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { Suspense, type FormEvent, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import type { UserLocale } from "../contracts";
import { SERVICE_MARK, SERVICE_NAME } from "../config/branding";
import { useI18n } from "../i18n/LocaleContext";
import type { TranslationKey } from "../i18n/translations";
import { Badge, Button, Dialog, Drawer, Popover, SelectField, Tooltip } from "./primitives";

interface NavigationItem {
  to: string;
  labelKey: TranslationKey;
  icon: LucideIcon;
  end: boolean;
  child?: boolean;
}

interface NavigationGroup {
  labelKey: TranslationKey;
  items: readonly NavigationItem[];
}

const NAVIGATION_GROUPS: readonly NavigationGroup[] = [
  {
    labelKey: "navigation.groupOverview",
    items: [{ to: "/", labelKey: "navigation.overview", icon: MonitorDot, end: true }],
  },
  {
    labelKey: "navigation.groupTriage",
    items: [
      { to: "/alerts", labelKey: "navigation.alerts", icon: BellRing, end: false },
      { to: "/incidents", labelKey: "navigation.incidents", icon: ShieldCheck, end: false },
    ],
  },
  {
    labelKey: "navigation.groupEvidence",
    items: [
      { to: "/endpoints", labelKey: "navigation.endpoints", icon: Server, end: false },
      { to: "/events", labelKey: "navigation.events", icon: Activity, end: false },
    ],
  },
  {
    labelKey: "navigation.groupAnalysis",
    items: [{ to: "/intelligence", labelKey: "navigation.intelligence", icon: Radar, end: false }],
  },
  {
    labelKey: "navigation.groupPlatform",
    items: [
      { to: "/operations", labelKey: "navigation.operations", icon: Database, end: true },
      { to: "/operations/archives", labelKey: "navigation.archives", icon: Archive, end: true, child: true },
    ],
  },
] as const;

const NAVIGATION_ITEMS = NAVIGATION_GROUPS.flatMap((group) => group.items);
const COMPACT_KEY = "edr.compactNavigation";

export function AppShell() {
  const auth = useAuth();
  const { dateLocale, locale, t } = useI18n();
  const location = useLocation();
  const navigate = useNavigate();
  const mobileMenuButtonRef = useRef<HTMLButtonElement>(null);
  const [compact, setCompact] = useState(() => localStorage.getItem(COMPACT_KEY) === "true");
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [localeSaving, setLocaleSaving] = useState(false);
  const [localeError, setLocaleError] = useState(false);
  const [search, setSearch] = useState("");
  const [reportOpen, setReportOpen] = useState(false);
  const breadcrumbs = buildBreadcrumbs(location.pathname, t);
  const pageTitleText = breadcrumbs.at(-1)?.label ?? t("navigation.console");
  const overviewRoute = location.pathname === "/";

  useEffect(() => { setMobileNavigationOpen(false); }, [location.pathname]);

  function toggleCompact(): void {
    setCompact((current) => {
      const next = !current;
      localStorage.setItem(COMPACT_KEY, String(next));
      return next;
    });
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
      <aside className="nav-rail desktop-navigation">
        <PrimaryNavigation compact={compact} onNavigate={() => undefined} onToggleCompact={toggleCompact} />
      </aside>
      <Drawer
        closeLabel={t("navigation.close")}
        label={t("navigation.primary")}
        onClose={() => setMobileNavigationOpen(false)}
        open={mobileNavigationOpen}
        returnFocusRef={mobileMenuButtonRef}
      >
        <PrimaryNavigation compact={false} mobile onNavigate={() => setMobileNavigationOpen(false)} onToggleCompact={toggleCompact} />
      </Drawer>
      <section className="console-shell">
        <header className="top-bar">
          <button
            aria-controls="mobile-primary-navigation"
            aria-expanded={mobileNavigationOpen}
            aria-label={t("navigation.toggle")}
            className="mobile-nav-menu icon-button"
            onClick={() => setMobileNavigationOpen(true)}
            ref={mobileMenuButtonRef}
            type="button"
          >
            <Menu aria-hidden="true" size={20} />
          </button>
          <div className={`top-title${overviewRoute ? " service-title" : ""}`}>
            {overviewRoute ? <strong title={SERVICE_NAME}>{SERVICE_NAME}</strong> : <>
              <Breadcrumbs items={breadcrumbs} label={t("navigation.breadcrumb")} />
              <strong>{pageTitleText}</strong>
            </>}
          </div>
          <div aria-label={t("navigation.investigationPath")} className="investigation-path">
            <span><Activity aria-hidden="true" size={14} />{t("navigation.pathSignal")}</span>
            <i aria-hidden="true" />
            <span><Search aria-hidden="true" size={14} />{t("navigation.pathEvidence")}</span>
            <i aria-hidden="true" />
            <span><ShieldCheck aria-hidden="true" size={14} />{t("navigation.pathDecision")}</span>
          </div>
          <form className="global-search" onSubmit={submitSearch} role="search">
            <Search aria-hidden="true" size={16} />
            <input aria-label={t("search.aria")} onChange={(event) => setSearch(event.target.value)} placeholder={t("search.placeholder")} value={search} />
          </form>
          <div className="session-summary">
            <div className="locale-control">
              <SelectField
                className="locale-selector"
                disabled={localeSaving}
                label={t("language.label")}
                onChange={(event) => void changeLocale(event.target.value as UserLocale)}
                value={locale}
              >
                <option value="EN">{t("language.english")}</option>
                <option value="KO">{t("language.korean")}</option>
              </SelectField>
              {localeError ? <span className="locale-error" role="alert">{t("language.saveError")}</span> : null}
            </div>
            <Popover label={t("navigation.accountMenu")} trigger={<CircleUserRound aria-hidden="true" size={19} />}>
              <div className="account-summary">
                <Badge tone="info">{auth.user?.role}</Badge>
                <strong>{auth.user?.name}</strong>
                <small>{auth.user?.loginId}</small>
              </div>
              <div className="account-actions">
                <Button onClick={() => setReportOpen(true)} type="button" variant="ghost"><Printer aria-hidden="true" size={17} />{t("report.openAria")}</Button>
                <Button onClick={() => auth.logout()} type="button" variant="ghost"><LogOut aria-hidden="true" size={17} />{t("navigation.logout")}</Button>
              </div>
            </Popover>
          </div>
        </header>
        <main className="main-content" id="main-content" tabIndex={-1}>
          <Suspense fallback={<div aria-label={t("common.loading")} className="route-loading" role="status"><span />{t("common.loading")}</div>}>
            <Outlet />
          </Suspense>
        </main>
        <Dialog
          actions={<>
            <Button onClick={() => setReportOpen(false)} type="button" variant="ghost">{t("report.cancel")}</Button>
            <Button onClick={() => window.print()} type="button"><Printer aria-hidden="true" size={16} />{t("report.printSave")}</Button>
          </>}
          closeLabel={t("report.close")}
          eyebrow="BROWSER REPORT"
          onClose={() => setReportOpen(false)}
          open={reportOpen}
          title={t("report.snapshot", { page: pageTitleText })}
        >
          <p>{t("report.description")}</p>
          <dl className="report-details">
            <div><dt>{t("report.page")}</dt><dd>{location.pathname}</dd></div>
            <div><dt>{t("report.generated")}</dt><dd>{new Date().toLocaleString(dateLocale)}</dd></div>
            <div><dt>{t("report.userRole")}</dt><dd>{auth.user?.role}</dd></div>
          </dl>
        </Dialog>
      </section>
    </div>
  );
}

function PrimaryNavigation({ compact, mobile = false, onNavigate, onToggleCompact }: {
  compact: boolean;
  mobile?: boolean;
  onNavigate: () => void;
  onToggleCompact: () => void;
}) {
  const { t } = useI18n();
  const compactLabel = compact ? t("navigation.expand") : t("navigation.compact");
  return <div className="navigation-content" id={mobile ? "mobile-primary-navigation" : undefined}>
    <div className="brand-mark" aria-label={SERVICE_NAME}>
      <span aria-hidden="true">{SERVICE_MARK}</span>
      <div><strong title={SERVICE_NAME}>{SERVICE_NAME}</strong><small>{t("navigation.endpointDefense")}</small></div>
    </div>
    <nav aria-label={t("navigation.primary")}>
      {NAVIGATION_GROUPS.map((group) => <section className="nav-group" key={group.labelKey}>
        <h2>{t(group.labelKey)}</h2>
        {group.items.map(({ to, labelKey, icon: Icon, end, child }) => {
          const label = t(labelKey);
          return <NavLink
            aria-label={label}
            className={({ isActive }) => `nav-item ${child ? "nav-child " : ""}${isActive ? "active" : ""}`.trim()}
            end={end}
            key={to}
            onClick={onNavigate}
            title={compact ? label : undefined}
            to={to}
          >
            <Icon aria-hidden="true" size={18} />
            <span>{label}</span>
          </NavLink>;
        })}
      </section>)}
    </nav>
    <div className="navigation-mode" aria-hidden="true"><span>EDR / SOC</span><small>{t("navigation.evidenceFirst")}</small></div>
    {!mobile ? <Tooltip label={compactLabel}>
      <button aria-label={compactLabel} className="nav-compact" onClick={onToggleCompact} type="button">
        {compact ? <PanelLeftOpen aria-hidden="true" size={18} /> : <PanelLeftClose aria-hidden="true" size={18} />}
        <span>{compact ? t("navigation.expand") : t("navigation.compact")}</span>
      </button>
    </Tooltip> : null}
  </div>;
}

function Breadcrumbs({ items, label }: { items: BreadcrumbItem[]; label: string }) {
  return <nav aria-label={label} className="breadcrumbs">
    <ol>
      <li><Link to="/">EDR</Link></li>
      {items.map((item, index) => <li key={`${item.label}-${item.to ?? "current"}`}>
        {item.to && index < items.length - 1 ? <Link to={item.to}>{item.label}</Link> : <span aria-current={index === items.length - 1 ? "page" : undefined}>{item.label}</span>}
      </li>)}
    </ol>
  </nav>;
}

interface BreadcrumbItem {
  label: string;
  to?: string;
}

function buildBreadcrumbs(pathname: string, t: ReturnType<typeof useI18n>["t"]): BreadcrumbItem[] {
  if (pathname === "/") return [{ label: t("navigation.overview") }];
  if (pathname === "/operations/archives") {
    return [
      { label: t("navigation.operations"), to: "/operations" },
      { label: t("navigation.archives") },
    ];
  }
  const matched = [...NAVIGATION_ITEMS]
    .sort((left, right) => right.to.length - left.to.length)
    .find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`));
  if (!matched) return [{ label: t("navigation.console") }];
  if (pathname === matched.to) return [{ label: t(matched.labelKey) }];
  const identifier = pathname.slice(matched.to.length + 1).split("/")[0];
  return [
    { label: t(matched.labelKey), to: matched.to },
    { label: `${t(matched.labelKey).replace(/s$/, "")} #${identifier}` },
  ];
}
