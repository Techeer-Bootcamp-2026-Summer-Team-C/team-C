import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { AlertDetailPage } from "./pages/AlertDetailPage";
import { AlertsPage } from "./pages/AlertsPage";
import { ArchivesPage } from "./pages/ArchivesPage";
import { EndpointDetailPage } from "./pages/EndpointDetailPage";
import { EndpointsPage } from "./pages/EndpointsPage";
import { EventDetailPage } from "./pages/EventDetailPage";
import { EventsPage } from "./pages/EventsPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { IntelligencePage } from "./pages/IntelligencePage";
import { LoginPage } from "./pages/LoginPage";
import { OperationsPage } from "./pages/OperationsPage";
import { OverviewPage } from "./pages/OverviewPage";

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
