import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import {
  DEFAULT_DASHBOARD_ID,
  createOverviewId,
  type CustomDashboardWidget,
  type CustomOverviewDashboard,
} from "./overviewLayoutModel";
import { readOverviewLayoutState, writeOverviewLayoutState, type StoredOverviewLayoutState } from "./overviewLayoutStorage";

interface OverviewLayoutValue extends StoredOverviewLayoutState {
  activeDashboard: CustomOverviewDashboard | null;
  selectDashboard: (dashboardId: string) => void;
  createDashboard: (name: string, widgets: CustomDashboardWidget[]) => string;
  updateDashboard: (dashboardId: string, name: string, widgets: CustomDashboardWidget[]) => void;
  deleteDashboard: (dashboardId: string) => void;
}

const OverviewLayoutContext = createContext<OverviewLayoutValue | null>(null);

export function OverviewLayoutProvider({ children, userId }: { children: ReactNode; userId: number }) {
  const [state, setState] = useState<StoredOverviewLayoutState>(() => readOverviewLayoutState(userId));

  const commit = useCallback((update: (current: StoredOverviewLayoutState) => StoredOverviewLayoutState) => {
    setState((current) => {
      const next = update(current);
      writeOverviewLayoutState(userId, next);
      return next;
    });
  }, [userId]);

  const selectDashboard = useCallback((dashboardId: string) => {
    commit((current) => ({
      ...current,
      activeDashboardId: dashboardId === DEFAULT_DASHBOARD_ID || current.dashboards.some((dashboard) => dashboard.id === dashboardId)
        ? dashboardId
        : DEFAULT_DASHBOARD_ID,
    }));
  }, [commit]);

  const createDashboard = useCallback((name: string, widgets: CustomDashboardWidget[]) => {
    const id = createOverviewId("dashboard");
    const now = new Date().toISOString();
    const dashboard: CustomOverviewDashboard = { id, name: name.trim(), widgets, createdAt: now, updatedAt: now };
    commit((current) => ({ dashboards: [...current.dashboards, dashboard], activeDashboardId: id }));
    return id;
  }, [commit]);

  const updateDashboard = useCallback((dashboardId: string, name: string, widgets: CustomDashboardWidget[]) => {
    commit((current) => ({
      ...current,
      dashboards: current.dashboards.map((dashboard) => dashboard.id === dashboardId
        ? { ...dashboard, name: name.trim(), widgets, updatedAt: new Date().toISOString() }
        : dashboard),
    }));
  }, [commit]);

  const deleteDashboard = useCallback((dashboardId: string) => {
    commit((current) => ({
      dashboards: current.dashboards.filter((dashboard) => dashboard.id !== dashboardId),
      activeDashboardId: current.activeDashboardId === dashboardId ? DEFAULT_DASHBOARD_ID : current.activeDashboardId,
    }));
  }, [commit]);

  const value = useMemo<OverviewLayoutValue>(() => ({
    ...state,
    activeDashboard: state.dashboards.find((dashboard) => dashboard.id === state.activeDashboardId) ?? null,
    selectDashboard,
    createDashboard,
    updateDashboard,
    deleteDashboard,
  }), [createDashboard, deleteDashboard, selectDashboard, state, updateDashboard]);

  return <OverviewLayoutContext.Provider value={value}>{children}</OverviewLayoutContext.Provider>;
}

export function useOverviewLayout(): OverviewLayoutValue {
  const value = useContext(OverviewLayoutContext);
  if (!value) throw new Error("useOverviewLayout must be used inside OverviewLayoutProvider");
  return value;
}
