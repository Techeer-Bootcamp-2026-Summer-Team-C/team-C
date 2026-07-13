import type { components, operations } from "./api/generated/schema";

type Schemas = components["schemas"];
type QueryOf<Operation extends keyof operations> = NonNullable<operations[Operation]["parameters"]["query"]>;

export type EndpointStatus = Schemas["EndpointStatus"];
export type OsType = Schemas["OsType"];
export type EventType = Schemas["EventType"];
export type Severity = Schemas["Severity"];
export type AlertStatus = Schemas["AlertStatus"];
export type IncidentStatus = Schemas["IncidentStatus"];
export type EventFailureStatus = Schemas["EventFailureStatus"];
export type StorageStatus = Schemas["StorageStatus"];
export type StorageBackend = Schemas["StorageBackend"];
export type StorageClass = Schemas["StorageClass"];
export type UserStatus = Schemas["UserStatus"];
export type UserRole = Schemas["UserRole"];
export type SensorHealth = Schemas["SensorHealth"];
export type AgentArchitecture = Schemas["AgentArchitecture"];
export type RiskLevel = Schemas["RiskLevel"];
export type EndpointRiskFactorSourceType = Schemas["EndpointRiskFactorSourceType"];
export type EdrStateStatus = Schemas["EdrStateStatus"];
export type EdrStateReasonCode = Schemas["EdrStateReasonCode"];
export type TimePreset = Schemas["TimePreset"];
export type DashboardInterval = Schemas["DashboardInterval"];
export type UtcTimestamp = Schemas["TimeRangeDto"]["from"];

export type RequestMeta = Schemas["RequestMeta"];
type GeneratedSuccessEnvelope = Schemas["SuccessEnvelope_LoginData_"];
export type SuccessEnvelope<Data> = Omit<GeneratedSuccessEnvelope, "data"> & { data: Data };
export type ErrorDetail = Schemas["ErrorDetail"];
export type ErrorEnvelope = Schemas["ErrorEnvelope"];
type GeneratedPagedData = Schemas["PagedData_EndpointDto_"];
export type PagedData<Item> = Omit<GeneratedPagedData, "items"> & { items: Item[] };

export type EndpointListQuery = QueryOf<"endpointsList">;
export type EventListQuery = QueryOf<"eventsList">;
export type EventDetailQuery = QueryOf<"eventsGet">;
export type ArchiveRestoreListQuery = QueryOf<"archiveRestoresList">;
export type AlertListQuery = QueryOf<"alertsList">;
export type IncidentListQuery = QueryOf<"incidentsList">;
export type DashboardSummaryQuery = QueryOf<"dashboardGetSummary">;
export type DashboardTimeQuery = QueryOf<"dashboardGetEndpointSummary">;
export type PaginationQuery = Pick<EndpointListQuery, "page" | "size">;
export type TimeRangeQuery = Pick<DashboardTimeQuery, "timePreset" | "from" | "to">;

export type LoginRequest = Schemas["LoginRequest"];
export type UserDto = Schemas["UserDto"];
export type LoginData = Schemas["LoginData"];
export type LogoutData = Schemas["LogoutData"];

export type AgentRegisterRequest = Schemas["AgentRegisterRequest"];
export type AgentRegisterData = Schemas["AgentRegisterData"];
export type SensorHealthSnapshot = Schemas["SensorHealthSnapshot"];
export type AgentHeartbeatRequest = Schemas["AgentHeartbeatRequest"];
export type AgentHeartbeatData = Schemas["AgentHeartbeatData"];
export type ProcessExecutionPayload = Schemas["ProcessExecutionPayload"];
export type NetworkConnectionPayload = Schemas["NetworkConnectionPayload"];
export type FileEventPayload = Schemas["FileEventPayload"];
export type DnsQueryPayload = Schemas["DnsQueryPayload"];
export type L7EventPayload = Schemas["L7EventPayload"];
export type TelemetryBatchRequest = Schemas["TelemetryBatchRequest"];
export type TelemetryEvent = TelemetryBatchRequest["events"][number];
export type RejectedEventDto = Schemas["RejectedEventDto"];
export type TelemetryBatchData = Schemas["TelemetryBatchData"];

export type SensorHealthDto = Schemas["SensorHealthDto"];
export type EndpointRiskFactorDto = Schemas["EndpointRiskFactorDto"];
export type EndpointRiskDto = Schemas["EndpointRiskDto"];
export type EndpointDto = Schemas["EndpointDto"];
export type CertificateDto = Schemas["CertificateDto"];
export type EndpointDetailDto = Schemas["EndpointDetailDto"];

export type EventDto = Schemas["EventDto"];
export type EventDetailDto = Schemas["EventDetailDto"];

export type ArchiveRestoreRequest = Schemas["ArchiveRestoreRequest"];
export type ArchiveBucketDto = Schemas["ArchiveBucketDto"];
export type ArchiveRestoreStartDto = Schemas["ArchiveRestoreStartDto"];

export type AlertDto = Schemas["AlertDto"];
export type ResponseGuidanceStepDto = Schemas["ResponseGuidanceStepDto"];
export type IncidentReferenceDto = Schemas["IncidentReferenceDto"];
export type AlertDetailDto = Schemas["AlertDetailDto"];
export type AlertStatusUpdateRequest = Schemas["AlertStatusUpdateRequest"];

export type IncidentDto = Schemas["IncidentDto"];
export type IncidentDetailDto = Schemas["IncidentDetailDto"];

export type TimeRangeDto = Schemas["TimeRangeDto"];
export type SeverityCountDto = Schemas["SeverityCountDto"];
export type AlertStatusCountDto = Schemas["AlertStatusCountDto"];
export type EventTypeCountDto = Schemas["EventTypeCountDto"];
export type FailureStatusCountDto = Schemas["FailureStatusCountDto"];
export type StorageBackendCountDto = Schemas["StorageBackendCountDto"];
export type StorageClassCountDto = Schemas["StorageClassCountDto"];
export type StorageStatusCountDto = Schemas["StorageStatusCountDto"];
export type OsTypeCountDto = Schemas["OsTypeCountDto"];
export type SensorHealthCountDto = Schemas["SensorHealthCountDto"];
export type TimeSeriesPointDto = Schemas["TimeSeriesPointDto"];
export type IncidentTimeSeriesPointDto = Schemas["IncidentTimeSeriesPointDto"];
export type TopRuleDto = Schemas["TopRuleDto"];
export type MitreTacticCountDto = Schemas["MitreTacticCountDto"];
export type MitreTechniqueCountDto = Schemas["MitreTechniqueCountDto"];
export type TopProcessDto = Schemas["TopProcessDto"];
export type TopRemoteIpDto = Schemas["TopRemoteIpDto"];
export type TopDomainDto = Schemas["TopDomainDto"];
export type TopFileHashDto = Schemas["TopFileHashDto"];
export type TopDnsQueryDto = Schemas["TopDnsQueryDto"];
export type TopL7ProtocolDto = Schemas["TopL7ProtocolDto"];
export type FailureStageCountDto = Schemas["FailureStageCountDto"];
export type FailureCodeCountDto = Schemas["FailureCodeCountDto"];
export type RiskLevelCountDto = Schemas["RiskLevelCountDto"];
export type EndpointRiskSummaryDto = Schemas["EndpointRiskSummaryDto"];
export type EdrStateAxisDto = Schemas["EdrStateAxisDto"];
export type EdrStateDto = Schemas["EdrStateDto"];
export type DashboardSummaryDto = Schemas["DashboardSummaryDto"];
export type EndpointSummaryDto = Schemas["EndpointSummaryDto"];
export type IngestSummaryDto = Schemas["IngestSummaryDto"];
