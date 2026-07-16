from collections import Counter
from datetime import UTC, datetime, timedelta
from math import ceil

from .api_services import endpoint_dto
from .contracts.alerts import ResponseGuidanceStepDto
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
    ResponseGuidanceSummaryDto,
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
from .errors import ApplicationError
from .event_service import EventService
from .policy.edr_state import CollectionHealthInput, ThreatLevelInput, calculate_edr_state
from .policy.risk import summarize_endpoint_risks
from .rule_loader import LoadedRule
from .storage.clickhouse import DASHBOARD_TOP_LIMIT, EventRepository, FailureRepository
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
        rules: list[LoadedRule] | None = None,
    ) -> None:
        self.endpoints = endpoints
        self.alerts = alerts
        self.incidents = incidents
        self.metadata = metadata
        self.events = events
        self.failures = failures
        self.event_service = event_service
        self.rules = {(item.rule.rule_code, item.rule.version): item for item in (rules or [])}

    def dashboard(
        self,
        *,
        from_: datetime,
        to: datetime,
        interval: DashboardInterval,
        calculated_at: datetime,
        endpoint_id: int | None = None,
    ) -> DashboardSummaryDto:
        seconds = {
            DashboardInterval.ONE_MINUTE: 60,
            DashboardInterval.FIVE_MINUTES: 300,
            DashboardInterval.ONE_HOUR: 3600,
            DashboardInterval.ONE_DAY: 86400,
        }[interval]
        if ceil((to - from_).total_seconds() / seconds) > 2000:
            raise ApplicationError(400, "VALIDATION_ERROR", "Dashboard interval exceeds 2,000 points.")
        endpoint_items = self._endpoint_items(calculated_at, endpoint_id=endpoint_id)
        alert_rows = self.alerts.list_rows(from_=from_, to=to, endpoint_id=endpoint_id)
        incident_rows = self.incidents.list_rows(from_=from_, to=to, endpoint_id=endpoint_id)
        event_summary = self.event_service.dashboard_summary(
            from_=from_,
            to=to,
            interval_seconds=seconds,
            endpoint_id=endpoint_id,
        )
        failure_rows = self.failures.current_rows(from_=from_, to=to, endpoint_id=endpoint_id)
        storage_rows = _filter_endpoint_rows(self.metadata.all_current(), endpoint_id)
        edr_state = self._edr_state(endpoint_items, calculated_at=calculated_at, endpoint_id=endpoint_id)

        alert_time = Counter(_bucket(row["detected_at"], seconds) for row in alert_rows)
        incident_time: dict[datetime, Counter[str]] = {}
        for row in incident_rows:
            incident_time.setdefault(_bucket(row["last_detected_at"], seconds), Counter())[str(row["status"])] += 1
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
                total_count=event_summary.total_count,
                by_event_type=[
                    EventTypeCountDto(event_type=value, count=event_summary.by_event_type[value.value])
                    for value in EventType
                    if event_summary.by_event_type[value.value]
                ],
                top_processes=[
                    TopProcessDto(process_name=value, count=count)
                    for value, count in _rank(event_summary.top_processes)[:DASHBOARD_TOP_LIMIT]
                ],
                top_remote_ips=[
                    TopRemoteIpDto(remote_ip=value, count=count)
                    for value, count in _rank(event_summary.top_remote_ips)[:DASHBOARD_TOP_LIMIT]
                ],
                top_domains=[
                    TopDomainDto(domain=value, count=count)
                    for value, count in _rank(event_summary.top_domains)[:DASHBOARD_TOP_LIMIT]
                ],
                top_file_hashes=[
                    TopFileHashDto(file_hash_sha256=value, count=count)
                    for value, count in _rank(event_summary.top_file_hashes)[:DASHBOARD_TOP_LIMIT]
                ],
                top_dns_queries=[
                    TopDnsQueryDto(dns_query=value, count=count)
                    for value, count in _rank(event_summary.top_dns_queries)[:DASHBOARD_TOP_LIMIT]
                ],
                top_l7_protocols=[
                    TopL7ProtocolDto(l7_protocol=value, count=count)
                    for value, count in _rank(event_summary.top_l7_protocols)[:DASHBOARD_TOP_LIMIT]
                ],
                time_series=[
                    TimeSeriesPointDto(bucket_start_at=_aware(key), count=value)
                    for key, value in sorted(event_summary.time_series.items())
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
            response_guidance=self._response_guidance(alert_rows),
        )

    def endpoint_summary(
        self,
        *,
        from_: datetime,
        to: datetime,
        calculated_at: datetime,
        endpoint_id: int | None = None,
    ) -> EndpointSummaryDto:
        endpoint_items = self._endpoint_items(calculated_at, endpoint_id=endpoint_id)
        alert_rows = self.alerts.list_rows(from_=from_, to=to, endpoint_id=endpoint_id)
        incident_rows = self.incidents.list_rows(from_=from_, to=to, endpoint_id=endpoint_id)
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

    def ingest_summary(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None = None,
    ) -> IngestSummaryDto:
        event_count, latest_ingested_at = self.events.ingest_summary(
            from_=from_, to=to, endpoint_id=endpoint_id
        )
        failures = self.failures.current_rows(from_=from_, to=to, endpoint_id=endpoint_id)
        storage = _filter_endpoint_rows(self.metadata.all_current(), endpoint_id)
        duration_minutes = max((to - from_).total_seconds() / 60, 1 / 60)
        return IngestSummaryDto(
            time_range=TimeRangeDto(from_=from_, to=to),
            events=IngestEventsDto(
                ingested_count=event_count,
                rate_per_minute=event_count / duration_minutes,
                latest_ingested_at=_aware(latest_ingested_at),
            ),
            event_failures=IngestEventFailuresDto(
                failed_count=sum(row["status"] == "FAILED" for row in failures),
                rate_per_minute=len(failures) / duration_minutes,
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

    def _response_guidance(self, alert_rows) -> ResponseGuidanceSummaryDto:
        active = [row for row in alert_rows if str(row["status"]) in {"OPEN", "IN_PROGRESS"}]
        identities = {(str(row["rule_code"]), int(row["rule_version"])) for row in active}
        candidates: list[tuple[int, int, object]] = []
        severity_rank = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}
        for identity in identities:
            loaded = self.rules.get(identity)
            if loaded is None:
                continue
            rank = severity_rank[loaded.rule.severity]
            for step in loaded.rule.response_guidance:
                candidates.append((rank, step.order, step))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2].title))
        seen: set[tuple[str, str, bool]] = set()
        steps: list[ResponseGuidanceStepDto] = []
        manual_action_count = 0
        for _rank, _order, step in candidates:
            key = (step.title, step.description, step.requires_manual_action)
            if key in seen:
                continue
            seen.add(key)
            manual_action_count += int(step.requires_manual_action)
            if len(steps) < 8:
                steps.append(ResponseGuidanceStepDto.model_validate(step.model_dump()))
        highest = max((Severity(str(row["severity"])) for row in active), key=severity_rank.get, default=None)
        return ResponseGuidanceSummaryDto(
            affected_alert_count=len(active),
            rule_count=len(identities),
            manual_action_step_count=manual_action_count,
            highest_severity=highest,
            steps=steps,
        )

    def _endpoint_items(self, calculated_at: datetime, *, endpoint_id: int | None = None):
        endpoint_ids = [endpoint_id] if endpoint_id is not None else None
        return [
            endpoint_dto(row, calculated_at=calculated_at)
            for row in self.endpoints.risk_snapshot(endpoint_ids=endpoint_ids)
        ]

    def _edr_state(
        self,
        endpoints,
        *,
        calculated_at: datetime,
        endpoint_id: int | None = None,
    ) -> EdrStateDto:
        risks = [item.risk for item in endpoints]
        risk_summary = summarize_endpoint_risks(risks, calculated_at=calculated_at)
        open_incidents = sum(item.risk.open_incident_count for item in endpoints)
        critical_alerts = sum(
            sum(alert["severity"] == "CRITICAL" for alert in row["active_alerts"])
            for row in self.endpoints.risk_snapshot(
                endpoint_ids=[endpoint_id] if endpoint_id is not None else None
            )
        )
        latest_ingest = self.events.latest_ingested_at(endpoint_id=endpoint_id)
        recent_failures = self.failures.current_rows(
            from_=calculated_at.replace(microsecond=0) - timedelta(minutes=15),
            to=calculated_at,
            endpoint_id=endpoint_id,
        )
        storage = _filter_endpoint_rows(self.metadata.all_current(), endpoint_id)
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


def _filter_endpoint_rows(rows, endpoint_id: int | None):
    if endpoint_id is None:
        return rows
    return [row for row in rows if int(row["endpoint_id"]) == endpoint_id]
