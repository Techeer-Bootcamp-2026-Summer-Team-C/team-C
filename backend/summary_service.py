from collections import Counter
from datetime import UTC, datetime, timedelta
from math import ceil

from .api_services import endpoint_dto
from .contracts.dashboard import (
    AlertStatusCountDto,
    DashboardAlertsDto,
    DashboardEndpointsDto,
    DashboardEventFailuresDto,
    DashboardEventsDto,
    DashboardIncidentsDto,
    DashboardStorageDto,
    DashboardSummaryDto,
    EdrStateAxisDto,
    EdrStateDto,
    EndpointRiskSummaryDto,
    EndpointSummaryAlertsDto,
    EndpointSummaryDto,
    EndpointSummaryIncidentsDto,
    EventTypeCountDto,
    FailureCodeCountDto,
    FailureStageCountDto,
    FailureStatusCountDto,
    IncidentTimeSeriesPointDto,
    IngestEventFailuresDto,
    IngestEventsDto,
    IngestStorageDto,
    IngestSummaryDto,
    MitreTacticCountDto,
    MitreTechniqueCountDto,
    OsTypeCountDto,
    RiskLevelCountDto,
    SensorHealthCountDto,
    SeverityCountDto,
    StorageBackendCountDto,
    StorageClassCountDto,
    StorageStatusCountDto,
    TimeRangeDto,
    TimeSeriesPointDto,
    TopDnsQueryDto,
    TopDomainDto,
    TopFileHashDto,
    TopL7ProtocolDto,
    TopProcessDto,
    TopRemoteIpDto,
    TopRuleDto,
)
from .contracts.enums import AlertStatus, DashboardInterval, EventFailureStatus, EventType, Severity
from .contracts.requests import EventListQuery
from .errors import ApplicationError
from .event_service import EventService
from .policy.edr_state import CollectionHealthInput, ThreatLevelInput, calculate_edr_state
from .policy.risk import summarize_endpoint_risks
from .storage.clickhouse import EventRepository, FailureRepository
from .storage.postgres import AlertRepository, EndpointRepository, IncidentRepository, IngestMetadataRepository


class SummaryService:
    def __init__(
        self,
        *,
        endpoints: EndpointRepository,
        alerts: AlertRepository,
        incidents: IncidentRepository,
        metadata: IngestMetadataRepository,
        events: EventRepository,
        failures: FailureRepository,
        event_service: EventService,
    ) -> None:
        self.endpoints = endpoints
        self.alerts = alerts
        self.incidents = incidents
        self.metadata = metadata
        self.events = events
        self.failures = failures
        self.event_service = event_service

    def dashboard(
        self,
        *,
        from_: datetime,
        to: datetime,
        interval: DashboardInterval,
        calculated_at: datetime,
    ) -> DashboardSummaryDto:
        seconds = {
            DashboardInterval.ONE_MINUTE: 60,
            DashboardInterval.FIVE_MINUTES: 300,
            DashboardInterval.ONE_HOUR: 3600,
            DashboardInterval.ONE_DAY: 86400,
        }[interval]
        if ceil((to - from_).total_seconds() / seconds) > 2000:
            raise ApplicationError(400, "VALIDATION_ERROR", "Dashboard interval exceeds 2,000 points.")
        endpoint_items = self._endpoint_items(calculated_at)
        alert_rows = self.alerts.list_rows(from_=from_, to=to)
        incident_rows = self.incidents.list_rows(from_=from_, to=to)
        event_items = self._event_items(from_, to)
        failure_rows = self.failures.current_rows(from_=from_, to=to)
        storage_rows = self.metadata.all_current()
        edr_state = self._edr_state(endpoint_items, calculated_at=calculated_at)

        alert_time = Counter(_bucket(row["detected_at"], seconds) for row in alert_rows)
        incident_time: dict[datetime, Counter[str]] = {}
        for row in incident_rows:
            incident_time.setdefault(_bucket(row["last_detected_at"], seconds), Counter())[str(row["status"])] += 1
        event_time = Counter(_bucket(item.occurred_at, seconds) for item in event_items)
        domains = [item.remote_domain or item.http_host for item in event_items if item.remote_domain or item.http_host]
        return DashboardSummaryDto(
            time_range=TimeRangeDto(from_=from_, to=to),
            interval=interval,
            edr_state=edr_state,
            alerts=DashboardAlertsDto(
                total_count=len(alert_rows),
                by_severity=_enum_counts(alert_rows, "severity", Severity, SeverityCountDto, "severity"),
                by_status=_enum_counts(alert_rows, "status", AlertStatus, AlertStatusCountDto, "status"),
                top_rules=[
                    TopRuleDto(rule_code=code, rule_name=name, count=count)
                    for (code, name), count in _rank(
                        Counter((row["rule_code"], row["rule_name"]) for row in alert_rows)
                    )
                ],
                mitre_tactics=[
                    MitreTacticCountDto(mitre_tactic_code=code, mitre_tactic_name=name, count=count)
                    for (code, name), count in _rank(
                        Counter((row["mitre_tactic_code"], row["mitre_tactic_name"]) for row in alert_rows)
                    )
                ],
                mitre_techniques=[
                    MitreTechniqueCountDto(mitre_technique_code=code, mitre_technique_name=name, count=count)
                    for (code, name), count in _rank(
                        Counter((row["mitre_technique_code"], row["mitre_technique_name"]) for row in alert_rows)
                    )
                ],
                time_series=[
                    TimeSeriesPointDto(bucket_start_at=key, count=value) for key, value in sorted(alert_time.items())
                ],
            ),
            incidents=DashboardIncidentsDto(
                open_count=sum(row["status"] == "OPEN" for row in incident_rows),
                closed_count=sum(row["status"] == "CLOSED" for row in incident_rows),
                by_severity=_enum_counts(incident_rows, "severity", Severity, SeverityCountDto, "severity"),
                time_series=[
                    IncidentTimeSeriesPointDto(
                        bucket_start_at=key,
                        open_count=counts["OPEN"],
                        closed_count=counts["CLOSED"],
                    )
                    for key, counts in sorted(incident_time.items())
                ],
            ),
            endpoints=_endpoint_counts(endpoint_items),
            events=DashboardEventsDto(
                total_count=len(event_items),
                by_event_type=_object_enum_counts(
                    event_items, "event_type", EventType, EventTypeCountDto, "event_type"
                ),
                top_processes=[
                    TopProcessDto(process_name=value, count=count)
                    for value, count in _rank_values(item.process_name for item in event_items)
                ],
                top_remote_ips=[
                    TopRemoteIpDto(remote_ip=value, count=count)
                    for value, count in _rank_values(item.remote_ip for item in event_items)
                ],
                top_domains=[TopDomainDto(domain=value, count=count) for value, count in _rank_values(domains)],
                top_file_hashes=[
                    TopFileHashDto(file_hash_sha256=value, count=count)
                    for value, count in _rank_values(item.file_hash_sha256 for item in event_items)
                ],
                top_dns_queries=[
                    TopDnsQueryDto(dns_query=value, count=count)
                    for value, count in _rank_values(item.dns_query for item in event_items)
                ],
                top_l7_protocols=[
                    TopL7ProtocolDto(l7_protocol=value, count=count)
                    for value, count in _rank_values(item.l7_protocol for item in event_items)
                ],
                time_series=[
                    TimeSeriesPointDto(bucket_start_at=key, count=value) for key, value in sorted(event_time.items())
                ],
            ),
            event_failures=DashboardEventFailuresDto(
                total_count=len(failure_rows),
                by_stage=[
                    FailureStageCountDto(failure_stage=value, count=count)
                    for value, count in _rank_values(row["failure_stage"] for row in failure_rows)
                ],
                by_code=[
                    FailureCodeCountDto(failure_code=value, count=count)
                    for value, count in _rank_nullable(row["failure_code"] for row in failure_rows)
                ],
                by_status=_enum_counts(failure_rows, "status", EventFailureStatus, FailureStatusCountDto, "status"),
            ),
            storage=DashboardStorageDto(
                total_bucket_count=len(storage_rows),
                by_backend=_string_counts(storage_rows, "storage_backend", StorageBackendCountDto, "storage_backend"),
                by_class=_string_counts(storage_rows, "storage_class", StorageClassCountDto, "storage_class"),
                by_status=_string_counts(storage_rows, "storage_status", StorageStatusCountDto, "storage_status"),
            ),
        )

    def endpoint_summary(self, *, from_: datetime, to: datetime, calculated_at: datetime) -> EndpointSummaryDto:
        endpoint_items = self._endpoint_items(calculated_at)
        alert_rows = self.alerts.list_rows(from_=from_, to=to)
        incident_rows = self.incidents.list_rows(from_=from_, to=to)
        summary = summarize_endpoint_risks([item.risk for item in endpoint_items], calculated_at=calculated_at)
        sensor_counter = Counter(
            (item.sensor, item.status) for endpoint in endpoint_items for item in endpoint.sensor_health
        )
        counts = _endpoint_counts(endpoint_items)
        return EndpointSummaryDto(
            time_range=TimeRangeDto(from_=from_, to=to),
            total_count=counts.total_count,
            online_count=counts.online_count,
            offline_count=counts.offline_count,
            retired_count=counts.retired_count,
            stale_count=counts.stale_count,
            by_os_type=[
                OsTypeCountDto(os_type=value, count=count)
                for value, count in _rank_values(item.os_type for item in endpoint_items)
            ],
            sensor_health=[
                SensorHealthCountDto(sensor=sensor, status=status, count=count)
                for (sensor, status), count in _rank(sensor_counter)
            ],
            risk=EndpointRiskSummaryDto(
                highest_score=summary.highest_score,
                high_risk_endpoint_count=summary.high_risk_endpoint_count,
                critical_risk_endpoint_count=summary.critical_risk_endpoint_count,
                by_level=[RiskLevelCountDto(level=level, count=count) for level, count in summary.by_level],
                calculated_at=calculated_at,
            ),
            alerts=EndpointSummaryAlertsDto(
                total_count=len(alert_rows),
                by_severity=_enum_counts(alert_rows, "severity", Severity, SeverityCountDto, "severity"),
            ),
            incidents=EndpointSummaryIncidentsDto(
                total_count=len(incident_rows),
                open_count=sum(row["status"] == "OPEN" for row in incident_rows),
                closed_count=sum(row["status"] == "CLOSED" for row in incident_rows),
                by_severity=_enum_counts(incident_rows, "severity", Severity, SeverityCountDto, "severity"),
            ),
        )

    def ingest_summary(self, *, from_: datetime, to: datetime) -> IngestSummaryDto:
        event_count, latest_ingested_at = self.events.ingest_summary(from_=from_, to=to)
        failures = self.failures.current_rows(from_=from_, to=to)
        storage = self.metadata.all_current()
        return IngestSummaryDto(
            time_range=TimeRangeDto(from_=from_, to=to),
            events=IngestEventsDto(ingested_count=event_count, latest_ingested_at=_aware(latest_ingested_at)),
            event_failures=IngestEventFailuresDto(
                failed_count=sum(row["status"] == "FAILED" for row in failures),
                reprocessed_count=sum(row["status"] == "REPROCESSED" for row in failures),
                reprocess_failed_count=sum(row["status"] == "REPROCESS_FAILED" for row in failures),
                oldest_failed_at=min(
                    (_aware(row["failed_at"]) for row in failures if row["status"] == "FAILED"),
                    default=None,
                ),
            ),
            storage=IngestStorageDto(
                clickhouse_hot_bucket_count=_storage_count(storage, "CLICKHOUSE", "HOT"),
                restored_bucket_count=_storage_count(storage, "S3", "RESTORED"),
                glacier_archived_bucket_count=_storage_count(storage, "S3", "ARCHIVED"),
                restoring_bucket_count=_storage_count(storage, "S3", "RESTORE_REQUESTED"),
                failed_bucket_count=_storage_count(storage, "S3", "RESTORE_FAILED"),
                expired_bucket_count=_storage_count(storage, "S3", "EXPIRED"),
            ),
        )

    def _endpoint_items(self, calculated_at: datetime):
        return [endpoint_dto(row, calculated_at=calculated_at) for row in self.endpoints.risk_snapshot()]

    def _event_items(self, from_: datetime, to: datetime):
        query = EventListQuery(timePreset="CUSTOM", **{"from": from_, "to": to}, page=1, size=500, sortOrder="asc")
        first = self.event_service.list_rows(query, from_=from_, to=to)
        items, total = first
        page = 2
        while len(items) < total:
            page_items, _ = self.event_service.list_rows(query.model_copy(update={"page": page}), from_=from_, to=to)
            items.extend(page_items)
            page += 1
        return items

    def _edr_state(self, endpoints, *, calculated_at: datetime) -> EdrStateDto:
        risks = [item.risk for item in endpoints]
        risk_summary = summarize_endpoint_risks(risks, calculated_at=calculated_at)
        open_incidents = sum(item.risk.open_incident_count for item in endpoints)
        critical_alerts = sum(
            sum(alert["severity"] == "CRITICAL" for alert in row["active_alerts"])
            for row in self.endpoints.risk_snapshot()
        )
        latest_ingest = self.events.ingest_summary(from_=datetime(1970, 1, 1, tzinfo=UTC), to=calculated_at)[1]
        recent_failures = self.failures.current_rows(
            from_=calculated_at.replace(microsecond=0) - timedelta(minutes=15),
            to=calculated_at,
        )
        storage = self.metadata.all_current()
        sensors = [
            sensor for endpoint in endpoints if endpoint.status != "RETIRED" for sensor in endpoint.sensor_health
        ]
        state = calculate_edr_state(
            ThreatLevelInput(
                risk_summary.highest_score,
                risk_summary.high_risk_endpoint_count,
                risk_summary.critical_risk_endpoint_count,
                open_incidents,
                critical_alerts,
            ),
            CollectionHealthInput(
                stale_count=sum(item.is_stale and item.status != "RETIRED" for item in endpoints),
                offline_non_stale_count=sum(item.status == "OFFLINE" and not item.is_stale for item in endpoints),
                degraded_sensor_count=sum(item.status == "DEGRADED" for item in sensors),
                unavailable_sensor_count=sum(item.status == "UNAVAILABLE" for item in sensors),
                non_retired_endpoint_count=sum(item.status != "RETIRED" for item in endpoints),
                latest_ingested_at=_aware(latest_ingest),
                failed_count_15m=sum(row["status"] == "FAILED" for row in recent_failures),
                reprocess_failed_count_15m=sum(row["status"] == "REPROCESS_FAILED" for row in recent_failures),
                restore_failed_bucket_count=sum(row["storage_status"] == "RESTORE_FAILED" for row in storage),
            ),
            calculated_at=calculated_at,
        )
        return EdrStateDto(
            status=state.status,
            score=state.score,
            threat_level=EdrStateAxisDto(
                status=state.threat_level.status,
                score=state.threat_level.score,
                reason_codes=list(state.threat_level.reason_codes),
            ),
            collection_health=EdrStateAxisDto(
                status=state.collection_health.status,
                score=state.collection_health.score,
                reason_codes=list(state.collection_health.reason_codes),
            ),
            highest_endpoint_risk_score=state.highest_endpoint_risk_score,
            high_risk_endpoint_count=state.high_risk_endpoint_count,
            critical_risk_endpoint_count=state.critical_risk_endpoint_count,
            reason_codes=list(state.reason_codes),
            calculated_at=calculated_at,
        )


def _endpoint_counts(items) -> DashboardEndpointsDto:
    return DashboardEndpointsDto(
        total_count=len(items),
        online_count=sum(item.status == "ONLINE" for item in items),
        offline_count=sum(item.status == "OFFLINE" for item in items),
        retired_count=sum(item.status == "RETIRED" for item in items),
        stale_count=sum(item.is_stale for item in items),
    )


def _enum_counts(rows, field, enum_type, dto_type, dto_field):
    counter = Counter(str(row[field]) for row in rows)
    return [
        dto_type(**{dto_field: value, "count": counter[value.value]}) for value in enum_type if counter[value.value]
    ]


def _object_enum_counts(rows, field, enum_type, dto_type, dto_field):
    counter = Counter(getattr(row, field) for row in rows)
    return [dto_type(**{dto_field: value, "count": counter[value]}) for value in enum_type if counter[value]]


def _string_counts(rows, field, dto_type, dto_field):
    return [dto_type(**{dto_field: value, "count": count}) for value, count in _rank_values(row[field] for row in rows)]


def _rank(counter):
    return sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))


def _rank_values(values):
    return _rank(Counter(value for value in values if value is not None and value != ""))


def _rank_nullable(values):
    return sorted(Counter(values).items(), key=lambda item: (-item[1], str(item[0])))


def _bucket(value, seconds):
    timestamp = _aware(value)
    epoch = int(timestamp.timestamp())
    return datetime.fromtimestamp((epoch // seconds) * seconds, tz=UTC)


def _aware(value):
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _storage_count(rows, backend, status):
    return sum(row["storage_backend"] == backend and row["storage_status"] == status for row in rows)
