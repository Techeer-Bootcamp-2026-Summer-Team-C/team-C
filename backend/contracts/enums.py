from enum import StrEnum


class EndpointStatus(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    RETIRED = "RETIRED"


class OsType(StrEnum):
    WINDOWS = "WINDOWS"
    MACOS = "MACOS"


class EventType(StrEnum):
    PROCESS_EXECUTION = "PROCESS_EXECUTION"
    NETWORK_CONNECTION = "NETWORK_CONNECTION"
    FILE_EVENT = "FILE_EVENT"
    DNS_QUERY = "DNS_QUERY"
    L7_EVENT = "L7_EVENT"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class EventFailureStatus(StrEnum):
    FAILED = "FAILED"
    REPROCESSED = "REPROCESSED"
    REPROCESS_FAILED = "REPROCESS_FAILED"


class StorageStatus(StrEnum):
    HOT = "HOT"
    ARCHIVED = "ARCHIVED"
    RESTORE_REQUESTED = "RESTORE_REQUESTED"
    RESTORED = "RESTORED"
    RESTORE_FAILED = "RESTORE_FAILED"
    EXPIRED = "EXPIRED"


class StorageBackend(StrEnum):
    CLICKHOUSE = "CLICKHOUSE"
    S3 = "S3"


class StorageClass(StrEnum):
    HOT = "HOT"
    GLACIER_FLEXIBLE_RETRIEVAL = "GLACIER_FLEXIBLE_RETRIEVAL"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class UserLocale(StrEnum):
    EN = "EN"
    KO = "KO"


class SensorHealth(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class WorkerStatus(StrEnum):
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class AgentArchitecture(StrEnum):
    X64 = "X64"
    ARM64 = "ARM64"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EndpointRiskFactorSourceType(StrEnum):
    ALERT = "ALERT"
    INCIDENT = "INCIDENT"


class EdrStateStatus(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class EdrStateReasonCode(StrEnum):
    MEDIUM_ENDPOINT_RISK = "MEDIUM_ENDPOINT_RISK"
    HIGH_ENDPOINT_RISK = "HIGH_ENDPOINT_RISK"
    CRITICAL_ENDPOINT_RISK = "CRITICAL_ENDPOINT_RISK"
    OPEN_INCIDENT = "OPEN_INCIDENT"
    CRITICAL_ALERT = "CRITICAL_ALERT"
    OFFLINE_ENDPOINT = "OFFLINE_ENDPOINT"
    STALE_ENDPOINT = "STALE_ENDPOINT"
    DEGRADED_SENSOR = "DEGRADED_SENSOR"
    UNAVAILABLE_SENSOR = "UNAVAILABLE_SENSOR"
    INGEST_FAILURE = "INGEST_FAILURE"
    INGEST_DELAYED = "INGEST_DELAYED"
    STORAGE_FAILURE = "STORAGE_FAILURE"


class TimePreset(StrEnum):
    LATEST_15M = "LATEST_15M"
    LATEST_1H = "LATEST_1H"
    LATEST_24H = "LATEST_24H"
    LATEST_7D = "LATEST_7D"
    CUSTOM = "CUSTOM"


class DashboardInterval(StrEnum):
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"


class DnsRecordType(StrEnum):
    A = "A"
    AAAA = "AAAA"
    MX = "MX"
    NS = "NS"
    PTR = "PTR"
