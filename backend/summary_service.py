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

MAX_SUMMARY_ENDPOINTS = 10_000


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
        alert_summary = self._alert_summary(
            from_=from_, to=to, endpoint_id=endpoint_id, interval_seconds=seconds
        )
        incident_summary = self._incident_summary(
            from_=from_, to=to, endpoint_id=endpoint_id, interval_seconds=seconds
        )
        event_summary = self.event_service.dashboard_summary(
            from_=from_,
            to=to,
            interval_seconds=seconds,
            endpoint_id=endpoint_id,
        )
        failure_summary = self._failure_summary(from_=from_, to=to, endpoint_id=endpoint_id)
        storage_summary = self._storage_summary(endpoint_id=endpoint_id)
        edr_state = self._edr_state(
            endpoint_items,
            storage_summary=storage_summary,
            calculated_at=calculated_at,
            endpoint_id=endpoint_id,
        )
        incident_time: dict[datetime, Counter[str]] = {}
        for row in incident_summary["time_series"]:
            incident_time.setdefault(_aware(row["bucket_start_at"]), Counter())[str(row["status"])] += int(
                row["count"]
            )
        return DashboardSummaryDto(
            time_range=TimeRangeDto(from_=from_, to=to),
            interval=interval,
            edr_state=edr_state,
            alerts=DashboardAlertsDto(
                total_count=alert_summary["total"],
                by_severity=_enum_count_map(
                    alert_summary["by_severity"], Severity, SeverityCountDto, "severity"
                ),
                by_status=_enum_count_map(
                    alert_summary["by_status"], AlertStatus, AlertStatusCountDto, "status"
                ),
                top_rules=[
                    TopRuleDto(
                        rule_code=row["rule_code"],
                        rule_name=row["rule_name"],
                        count=row["event_count"],
                    )
                    for row in alert_summary["top_rules"]
                ],
                mitre_tactics=[
                    MitreTacticCountDto(
                        mitre_tactic_code=row["mitre_tactic_code"],
                        mitre_tactic_name=row["mitre_tactic_name"],
                        count=row["event_count"],
                    )
                    for row in alert_summary["mitre_tactics"]
                ],
                mitre_techniques=[
                    MitreTechniqueCountDto(
                        mitre_technique_code=row["mitre_technique_code"],
                        mitre_technique_name=row["mitre_technique_name"],
                        count=row["event_count"],
                    )
                    for row in alert_summary["mitre_techniques"]
                ],
                time_series=[
                    TimeSeriesPointDto(bucket_start_at=key, count=value)
                    for key, value in sorted(alert_summary["time_series"].items())
                ],
            ),
            incidents=DashboardIncidentsDto(
                open_count=incident_summary["by_status"].get("OPEN", 0),
                closed_count=incident_summary["by_status"].get("CLOSED", 0),
                by_severity=_enum_count_map(
                    incident_summary["by_severity"], Severity, SeverityCountDto, "severity"
                ),
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
                total_count=failure_summary["total"],
                by_stage=[
                    FailureStageCountDto(failure_stage=value, count=count)
                    for value, count in _rank(Counter(failure_summary["by_stage"]))
                ],
                by_code=[
                    FailureCodeCountDto(failure_code=value, count=count)
                    for value, count in _rank(Counter(failure_summary["by_code"]))
                ],
                by_status=_enum_count_map(
                    failure_summary["by_status"],
                    EventFailureStatus,
                    FailureStatusCountDto,
                    "status",
                ),
            ),
            storage=DashboardStorageDto(
                total_bucket_count=storage_summary["total"],
                by_backend=_string_count_map(
                    storage_summary["by_backend"], StorageBackendCountDto, "storage_backend"
                ),
                by_class=_string_count_map(storage_summary["by_class"], StorageClassCountDto, "storage_class"),
                by_status=_string_count_map(
                    storage_summary["by_status"], StorageStatusCountDto, "storage_status"
                ),
            ),
            response_guidance=self._response_guidance_summary(alert_summary["active_rules"]),
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
        alert_summary = self._alert_summary(
            from_=from_, to=to, endpoint_id=endpoint_id, interval_seconds=86400
        )
        incident_summary = self._incident_summary(
            from_=from_, to=to, endpoint_id=endpoint_id, interval_seconds=86400
        )
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
                total_count=alert_summary["total"],
                by_severity=_enum_count_map(
                    alert_summary["by_severity"], Severity, SeverityCountDto, "severity"
                ),
            ),
            incidents=EndpointSummaryIncidentsDto(
                total_count=sum(incident_summary["by_status"].values()),
                open_count=incident_summary["by_status"].get("OPEN", 0),
                closed_count=incident_summary["by_status"].get("CLOSED", 0),
                by_severity=_enum_count_map(
                    incident_summary["by_severity"], Severity, SeverityCountDto, "severity"
                ),
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
        failures = self._failure_summary(from_=from_, to=to, endpoint_id=endpoint_id)
        storage = self._storage_summary(endpoint_id=endpoint_id)
        duration_minutes = max((to - from_).total_seconds() / 60, 1 / 60)
        return IngestSummaryDto(
            time_range=TimeRangeDto(from_=from_, to=to),
            events=IngestEventsDto(
                ingested_count=event_count,
                rate_per_minute=event_count / duration_minutes,
                latest_ingested_at=_aware(latest_ingested_at),
            ),
            event_failures=IngestEventFailuresDto(
                failed_count=failures["by_status"].get("FAILED", 0),
                rate_per_minute=failures["total"] / duration_minutes,
                reprocessed_count=failures["by_status"].get("REPROCESSED", 0),
                reprocess_failed_count=failures["by_status"].get("REPROCESS_FAILED", 0),
                oldest_failed_at=_aware(failures["oldest_failed_at"]),
            ),
            storage=IngestStorageDto(
                clickhouse_hot_bucket_count=storage["by_status"].get("HOT", 0),
                restored_bucket_count=storage["by_status"].get("RESTORED", 0),
                glacier_archived_bucket_count=storage["by_status"].get("ARCHIVED", 0),
                restoring_bucket_count=storage["by_status"].get("RESTORE_REQUESTED", 0),
                failed_bucket_count=storage["by_status"].get("RESTORE_FAILED", 0),
                expired_bucket_count=storage["by_status"].get("EXPIRED", 0),
            ),
        )

    def _alert_summary(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None,
        interval_seconds: int,
    ) -> dict:
        aggregate = getattr(self.alerts, "summary", None)
        if callable(aggregate):
            return aggregate(
                from_=from_,
                to=to,
                endpoint_id=endpoint_id,
                interval_seconds=interval_seconds,
            )
        rows = self.alerts.list_rows(from_=from_, to=to, endpoint_id=endpoint_id)
        active = [row for row in rows if str(row["status"]) in {"OPEN", "IN_PROGRESS"}]
        active_rules = Counter(
            (str(row["rule_code"]), int(row["rule_version"]), str(row["severity"]))
            for row in active
        )
        return {
            "total": len(rows),
            "by_severity": dict(Counter(str(row["severity"]) for row in rows)),
            "by_status": dict(Counter(str(row["status"]) for row in rows)),
            "top_rules": [
                {"rule_code": code, "rule_name": name, "event_count": count}
                for (code, name), count in _rank(
                    Counter((row["rule_code"], row["rule_name"]) for row in rows)
                )
            ],
            "mitre_tactics": [
                {
                    "mitre_tactic_code": code,
                    "mitre_tactic_name": name,
                    "event_count": count,
                }
                for (code, name), count in _rank(
                    Counter((row["mitre_tactic_code"], row["mitre_tactic_name"]) for row in rows)
                )
            ],
            "mitre_techniques": [
                {
                    "mitre_technique_code": code,
                    "mitre_technique_name": name,
                    "event_count": count,
                }
                for (code, name), count in _rank(
                    Counter((row["mitre_technique_code"], row["mitre_technique_name"]) for row in rows)
                )
            ],
            "time_series": dict(Counter(_bucket(row["detected_at"], interval_seconds) for row in rows)),
            "active_rules": [
                {
                    "rule_code": code,
                    "rule_version": version,
                    "severity": severity,
                    "count": count,
                }
                for (code, version, severity), count in active_rules.items()
            ],
        }

    def _incident_summary(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_id: int | None,
        interval_seconds: int,
    ) -> dict:
        aggregate = getattr(self.incidents, "summary", None)
        if callable(aggregate):
            return aggregate(
                from_=from_,
                to=to,
                endpoint_id=endpoint_id,
                interval_seconds=interval_seconds,
            )
        rows = self.incidents.list_rows(from_=from_, to=to, endpoint_id=endpoint_id)
        time_counts = Counter(
            (_bucket(row["last_detected_at"], interval_seconds), str(row["status"]))
            for row in rows
        )
        return {
            "by_status": dict(Counter(str(row["status"]) for row in rows)),
            "by_severity": dict(Counter(str(row["severity"]) for row in rows)),
            "time_series": [
                {
                    "bucket_start_at": bucket,
                    "status": status,
                    "count": count,
                }
                for (bucket, status), count in time_counts.items()
            ],
        }

    def _failure_summary(self, *, from_: datetime, to: datetime, endpoint_id: int | None) -> dict:
        aggregate = getattr(self.failures, "summary", None)
        if callable(aggregate):
            return aggregate(from_=from_, to=to, endpoint_id=endpoint_id)
        rows = self.failures.current_rows(from_=from_, to=to, endpoint_id=endpoint_id)
        return {
            "total": len(rows),
            "oldest_failed_at": min(
                (_aware(row["failed_at"]) for row in rows if row["status"] == "FAILED"),
                default=None,
            ),
            "by_stage": dict(
                Counter(str(row["failure_stage"]) for row in rows if row.get("failure_stage"))
            ),
            "by_code": dict(Counter(row.get("failure_code") for row in rows if row.get("failure_code"))),
            "by_status": dict(Counter(str(row["status"]) for row in rows)),
        }

    def _storage_summary(self, *, endpoint_id: int | None) -> dict:
        aggregate = getattr(self.metadata, "summary", None)
        if callable(aggregate):
            return aggregate(endpoint_id=endpoint_id)
        rows = _filter_endpoint_rows(self.metadata.all_current(), endpoint_id)
        return {
            "total": len(rows),
            "by_backend": dict(Counter(str(row["storage_backend"]) for row in rows)),
            "by_class": dict(Counter(str(row.get("storage_class")) for row in rows if row.get("storage_class"))),
            "by_status": dict(Counter(str(row["storage_status"]) for row in rows)),
        }

    def _response_guidance_summary(self, active_rules: list[dict]) -> ResponseGuidanceSummaryDto:
        identities = {(str(row["rule_code"]), int(row["rule_version"])) for row in active_rules}
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
        highest = max(
            (Severity(str(row["severity"])) for row in active_rules),
            key=severity_rank.get,
            default=None,
        )
        return ResponseGuidanceSummaryDto(
            affected_alert_count=sum(int(row["count"]) for row in active_rules),
            rule_count=len(identities),
            manual_action_step_count=manual_action_count,
            highest_severity=highest,
            steps=steps,
        )

    def _endpoint_items(self, calculated_at: datetime, *, endpoint_id: int | None = None):
        endpoint_ids = [endpoint_id] if endpoint_id is not None else None
        risk_page = getattr(self.endpoints, "risk_page", None)
        if callable(risk_page):
            rows, total = risk_page(
                endpoint_ids=endpoint_ids,
                limit=MAX_SUMMARY_ENDPOINTS + 1,
                offset=0,
            )
            if total > MAX_SUMMARY_ENDPOINTS:
                raise ApplicationError(
                    400,
                    "VALIDATION_ERROR",
                    f"Endpoint summary exceeds {MAX_SUMMARY_ENDPOINTS} endpoints; select an Endpoint filter.",
                )
            return [endpoint_dto(row, calculated_at=calculated_at) for row in rows]
        return [
            endpoint_dto(row, calculated_at=calculated_at)
            for row in self.endpoints.risk_snapshot(endpoint_ids=endpoint_ids)
        ]

    def _edr_state(
        self,
        endpoints,
        *,
        storage_summary: dict,
        calculated_at: datetime,
        endpoint_id: int | None = None,
    ) -> EdrStateDto:
        risks = [item.risk for item in endpoints]
        risk_summary = summarize_endpoint_risks(risks, calculated_at=calculated_at)
        open_incidents = sum(item.risk.open_incident_count for item in endpoints)
        active_severity_count = getattr(self.alerts, "active_severity_count", None)
        if callable(active_severity_count):
            critical_alerts = active_severity_count(endpoint_id=endpoint_id, severity="CRITICAL")
        else:
            critical_alerts = sum(
                sum(alert["severity"] == "CRITICAL" for alert in row["active_alerts"])
                for row in self.endpoints.risk_snapshot(
                    endpoint_ids=[endpoint_id] if endpoint_id is not None else None
                )
            )
        latest_ingest = self.events.latest_ingested_at(endpoint_id=endpoint_id)
        recent_failures = self._failure_summary(
            from_=calculated_at.replace(microsecond=0) - timedelta(minutes=15),
            to=calculated_at,
            endpoint_id=endpoint_id,
        )
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
                failed_count_15m=recent_failures["by_status"].get("FAILED", 0),
                reprocess_failed_count_15m=recent_failures["by_status"].get("REPROCESS_FAILED", 0),
                restore_failed_bucket_count=storage_summary["by_status"].get("RESTORE_FAILED", 0),
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


def _enum_count_map(counts, enum_type, dto_type, dto_field):
    return [
        dto_type(**{dto_field: value, "count": int(counts.get(value.value, 0))})
        for value in enum_type
        if counts.get(value.value, 0)
    ]


def _string_count_map(counts, dto_type, dto_field):
    return [
        dto_type(**{dto_field: value, "count": int(count)})
        for value, count in _rank(Counter(counts))
    ]


def _rank(counter):
    return sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))


def _rank_values(values):
    return _rank(Counter(value for value in values if value is not None and value != ""))


def _bucket(value, seconds):
    timestamp = _aware(value)
    epoch = int(timestamp.timestamp())
    return datetime.fromtimestamp((epoch // seconds) * seconds, tz=UTC)


def _aware(value):
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _filter_endpoint_rows(rows, endpoint_id: int | None):
    if endpoint_id is None:
        return rows
    return [row for row in rows if int(row["endpoint_id"]) == endpoint_id]
