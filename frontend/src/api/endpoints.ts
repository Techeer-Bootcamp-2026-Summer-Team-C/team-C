import type {
  AlertDetailDto,
  AlertDto,
  AlertListQuery,
  AlertStatusUpdateRequest,
  ArchiveRestoreListQuery,
  ArchiveRestoreRequest,
  ArchiveRestoreStartDto,
  DashboardSummaryDto,
  DashboardSummaryQuery,
  DashboardTimeQuery,
  EndpointDetailDto,
  EndpointDto,
  EndpointListQuery,
  EndpointSummaryDto,
  EventDetailDto,
  EventDetailQuery,
  EventDto,
  EventListQuery,
  IncidentDetailDto,
  IncidentDto,
  IncidentListQuery,
  IngestSummaryDto,
  LoginData,
  LoginRequest,
  PagedData,
  SuccessEnvelope,
  UserDto,
  UserLocaleUpdateRequest,
} from "../contracts";
import { apiRequest, buildQuery } from "./client";

type QueryRecord = Record<string, string | number | readonly number[] | undefined | null>;

function queryRecord(query: object): QueryRecord {
  return query as QueryRecord;
}

export const api = {
  login(body: LoginRequest, signal?: AbortSignal): Promise<SuccessEnvelope<LoginData>> {
    return apiRequest("/auth/login", { method: "POST", body: JSON.stringify(body) }, signal);
  },
  currentUser(signal?: AbortSignal): Promise<SuccessEnvelope<UserDto>> {
    return apiRequest("/users/me", {}, signal);
  },
  updateLocale(body: UserLocaleUpdateRequest, signal?: AbortSignal): Promise<SuccessEnvelope<UserDto>> {
    return apiRequest("/users/me/locale", { method: "PATCH", body: JSON.stringify(body) }, signal);
  },
  endpoints(query: EndpointListQuery, signal?: AbortSignal): Promise<SuccessEnvelope<PagedData<EndpointDto>>> {
    return apiRequest(`/endpoints${buildQuery(queryRecord(query))}`, {}, signal);
  },
  endpoint(endpointId: number, signal?: AbortSignal): Promise<SuccessEnvelope<EndpointDetailDto>> {
    return apiRequest(`/endpoints/${endpointId}`, {}, signal);
  },
  events(query: EventListQuery, signal?: AbortSignal): Promise<SuccessEnvelope<PagedData<EventDto>>> {
    return apiRequest(`/events${buildQuery(queryRecord(query))}`, {}, signal);
  },
  event(eventId: string, query: EventDetailQuery, signal?: AbortSignal): Promise<SuccessEnvelope<EventDetailDto>> {
    return apiRequest(`/events/${encodeURIComponent(eventId)}${buildQuery(queryRecord(query))}`, {}, signal);
  },
  alerts(query: AlertListQuery, signal?: AbortSignal): Promise<SuccessEnvelope<PagedData<AlertDto>>> {
    return apiRequest(`/alerts${buildQuery(queryRecord(query))}`, {}, signal);
  },
  alert(alertId: number, signal?: AbortSignal): Promise<SuccessEnvelope<AlertDetailDto>> {
    return apiRequest(`/alerts/${alertId}`, {}, signal);
  },
  updateAlert(
    alertId: number,
    body: AlertStatusUpdateRequest,
    signal?: AbortSignal,
  ): Promise<SuccessEnvelope<AlertDto>> {
    return apiRequest(`/alerts/${alertId}/status`, { method: "PATCH", body: JSON.stringify(body) }, signal);
  },
  incidents(query: IncidentListQuery, signal?: AbortSignal): Promise<SuccessEnvelope<PagedData<IncidentDto>>> {
    return apiRequest(`/incidents${buildQuery(queryRecord(query))}`, {}, signal);
  },
  incident(incidentId: number, signal?: AbortSignal): Promise<SuccessEnvelope<IncidentDetailDto>> {
    return apiRequest(`/incidents/${incidentId}`, {}, signal);
  },
  dashboard(query: DashboardSummaryQuery, signal?: AbortSignal): Promise<SuccessEnvelope<DashboardSummaryDto>> {
    return apiRequest(`/dashboard/summary${buildQuery(queryRecord(query))}`, {}, signal);
  },
  endpointSummary(query: DashboardTimeQuery, signal?: AbortSignal): Promise<SuccessEnvelope<EndpointSummaryDto>> {
    return apiRequest(`/dashboard/endpoints/summary${buildQuery(queryRecord(query))}`, {}, signal);
  },
  ingestSummary(query: DashboardTimeQuery, signal?: AbortSignal): Promise<SuccessEnvelope<IngestSummaryDto>> {
    return apiRequest(`/dashboard/ingest/summary${buildQuery(queryRecord(query))}`, {}, signal);
  },
  archives(
    query: ArchiveRestoreListQuery,
    signal?: AbortSignal,
  ): Promise<SuccessEnvelope<PagedData<import("../contracts").ArchiveBucketDto>>> {
    return apiRequest(`/archives/restores${buildQuery(queryRecord(query))}`, {}, signal);
  },
  startRestore(
    body: ArchiveRestoreRequest,
    signal?: AbortSignal,
  ): Promise<SuccessEnvelope<ArchiveRestoreStartDto>> {
    return apiRequest("/archives/restores", { method: "POST", body: JSON.stringify(body) }, signal);
  },
};
