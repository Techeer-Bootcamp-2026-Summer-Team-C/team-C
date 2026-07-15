from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApiContract:
    method: str
    path: str
    request: str
    response_data: str
    auth: str


PRODUCT_API_CONTRACTS: tuple[ApiContract, ...] = (
    ApiContract("POST", "/auth/login", "LoginRequest", "LoginData", "PUBLIC"),
    ApiContract("GET", "/users/me", "none", "UserDto", "JWT_READ"),
    ApiContract("PATCH", "/users/me/locale", "UserLocaleUpdateRequest", "UserDto", "JWT_READ"),
    ApiContract("GET", "/endpoints", "EndpointListQuery", "PagedData<EndpointDto>", "JWT_READ"),
    ApiContract("GET", "/endpoints/{endpointId}", "path", "EndpointDetailDto", "JWT_READ"),
    ApiContract("GET", "/endpoints/{endpointId}/process-tree", "ProcessTreeQuery", "ProcessTreeDto", "JWT_READ"),
    ApiContract("GET", "/events", "EventListQuery", "PagedData<EventDto>", "JWT_READ"),
    ApiContract("GET", "/events/{eventId}", "EventDetailQuery", "EventDetailDto", "JWT_READ"),
    ApiContract("GET", "/failures", "FailureListQuery", "PagedData<EventFailureDto>", "JWT_READ"),
    ApiContract("POST", "/archives/restores", "ArchiveRestoreRequest", "ArchiveRestoreStartDto", "JWT_WRITE"),
    ApiContract("GET", "/archives/restores", "ArchiveRestoreListQuery", "PagedData<ArchiveBucketDto>", "JWT_READ"),
    ApiContract("GET", "/alerts", "AlertListQuery", "PagedData<AlertDto>", "JWT_READ"),
    ApiContract("GET", "/alerts/{alertId}", "path", "AlertDetailDto", "JWT_READ"),
    ApiContract("PATCH", "/alerts/{alertId}/status", "AlertStatusUpdateRequest", "AlertDto", "JWT_WRITE"),
    ApiContract("GET", "/incidents", "IncidentListQuery", "PagedData<IncidentDto>", "JWT_READ"),
    ApiContract("GET", "/incidents/{incidentId}", "path", "IncidentDetailDto", "JWT_READ"),
    ApiContract("GET", "/incidents/{incidentId}/timeline", "path", "AttackTimelineDto", "JWT_READ"),
    ApiContract("GET", "/dashboard/summary", "DashboardSummaryQuery", "DashboardSummaryDto", "JWT_READ"),
    ApiContract("GET", "/dashboard/layouts/{dashboardKey}", "path", "DashboardLayoutDto", "JWT_READ"),
    ApiContract(
        "PUT",
        "/dashboard/layouts/{dashboardKey}",
        "DashboardLayoutPutRequest",
        "DashboardLayoutDto",
        "JWT_USER_WRITE",
    ),
    ApiContract("DELETE", "/dashboard/layouts/{dashboardKey}", "path", "DashboardLayoutDto", "JWT_USER_WRITE"),
    ApiContract("GET", "/dashboard/endpoints/summary", "DashboardTimeQuery", "EndpointSummaryDto", "JWT_READ"),
    ApiContract("GET", "/dashboard/ingest/summary", "DashboardTimeQuery", "IngestSummaryDto", "JWT_READ"),
    ApiContract("GET", "/dashboard/topology", "TopologyQuery", "EgressTopologyDto", "JWT_READ"),
    ApiContract("GET", "/operations/health", "none", "OperationsHealthDto", "JWT_READ"),
    ApiContract("POST", "/collector/agents/register", "AgentRegisterRequest", "AgentRegisterData", "MTLS_REGISTER"),
    ApiContract("POST", "/collector/agents/heartbeat", "AgentHeartbeatRequest", "AgentHeartbeatData", "MTLS_ACTIVE"),
    ApiContract("POST", "/collector/telemetry/batches", "TelemetryBatchRequest", "TelemetryBatchData", "MTLS_ACTIVE"),
)
