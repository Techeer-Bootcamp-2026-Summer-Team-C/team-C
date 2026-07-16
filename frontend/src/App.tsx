import { lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { LoginPage } from "./pages/LoginPage";

const AlertDetailPage = lazy(async () => ({ default: (await import("./pages/AlertDetailPage")).AlertDetailPage }));
const AlertsPage = lazy(async () => ({ default: (await import("./pages/AlertsPage")).AlertsPage }));
const ArchivesPage = lazy(async () => ({ default: (await import("./pages/ArchivesPage")).ArchivesPage }));
const EndpointDetailPage = lazy(async () => ({ default: (await import("./pages/EndpointDetailPage")).EndpointDetailPage }));
const EndpointsPage = lazy(async () => ({ default: (await import("./pages/EndpointsPage")).EndpointsPage }));
const EventDetailPage = lazy(async () => ({ default: (await import("./pages/EventDetailPage")).EventDetailPage }));
const EventsPage = lazy(async () => ({ default: (await import("./pages/EventsPage")).EventsPage }));
const IncidentDetailPage = lazy(async () => ({ default: (await import("./pages/IncidentDetailPage")).IncidentDetailPage }));
const IncidentsPage = lazy(async () => ({ default: (await import("./pages/IncidentsPage")).IncidentsPage }));
const IntelligencePage = lazy(async () => ({ default: (await import("./pages/IntelligencePage")).IntelligencePage }));
const OperationsPage = lazy(async () => ({ default: (await import("./pages/OperationsPage")).OperationsPage }));
const OverviewPage = lazy(async () => ({ default: (await import("./pages/OverviewPage")).OverviewPage }));

export function App() {
  return <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<RequireAuth><AppShell /></RequireAuth>}>
      <Route index element={<OverviewPage />} />
      <Route path="alerts" element={<AlertsPage />} />
      <Route path="alerts/:alertId" element={<AlertDetailPage />} />
      <Route path="incidents" element={<IncidentsPage />} />
      <Route path="incidents/:incidentId" element={<IncidentDetailPage />} />
      <Route path="endpoints" element={<EndpointsPage />} />
      <Route path="endpoints/:endpointId" element={<EndpointDetailPage />} />
      <Route path="events" element={<EventsPage />} />
      <Route path="events/:eventId" element={<EventDetailPage />} />
      <Route path="intelligence" element={<IntelligencePage />} />
      <Route path="operations" element={<OperationsPage />} />
      <Route path="operations/archives" element={<ArchivesPage />} />
    </Route>
    <Route path="*" element={<Navigate replace to="/" />} />
  </Routes>;
}
