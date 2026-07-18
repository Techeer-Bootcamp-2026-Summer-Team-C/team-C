from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from .contracts.alerts import (
    AlertDetailDto,
    AlertDto,
    IncidentReferenceDto,
    ResponseGuidanceStepDto,
)
from .contracts.common import PagedData
from .contracts.endpoints import CertificateDto, EndpointDetailDto, EndpointDto, EndpointRiskDto, SensorHealthDto
from .contracts.enums import Severity
from .contracts.incidents import IncidentDetailDto, IncidentDto
from .contracts.requests import AlertListQuery, EndpointListQuery, IncidentListQuery
from .errors import ApplicationError
from .event_service import EventService
from .policy.risk import AlertRiskInput, IncidentRiskInput, calculate_endpoint_risk
from .rule_loader import LoadedRule
from .storage.postgres import AlertRepository, EndpointRepository, IncidentRepository


class EndpointService:
    def __init__(self, repository: EndpointRepository) -> None:
        self.repository = repository

    def list(self, query: EndpointListQuery, *, calculated_at: datetime) -> PagedData[EndpointDto]:
        rows, total = self.repository.risk_page(
            endpoint_ids=query.endpoint_ids,
            q=query.q,
            status=query.status,
            os_type=query.os_type,
            risk_level=query.risk_level,
            sort_by=query.sort_by,
            sort_order=query.sort_order,
            limit=query.size,
            offset=(query.page - 1) * query.size,
        )
        items = [endpoint_dto(row, calculated_at=calculated_at) for row in rows]
        return PagedData(items=items, page=query.page, size=query.size, total=total)

    def detail(self, endpoint_id: int, *, calculated_at: datetime) -> EndpointDetailDto:
        row = next(iter(self.repository.risk_snapshot(endpoint_ids=[endpoint_id])), None)
        if row is None:
            raise ApplicationError(404, "NOT_FOUND", "Endpoint was not found.")
        base = endpoint_dto(row, calculated_at=calculated_at).model_dump()
        certificates = []
        for certificate in self.repository.certificates(endpoint_id):
            expires_at = _timestamp(certificate["expires_at"])
            revoked_at = _timestamp(certificate["revoked_at"]) if certificate["revoked_at"] else None
            certificates.append(
                CertificateDto(
                    cert_fingerprint=certificate["cert_fingerprint"],
                    cert_subject=certificate["cert_subject"],
                    cert_san_agent_id=certificate["cert_san_agent_id"],
                    expires_at=expires_at,
                    issued_at=_timestamp(certificate["issued_at"]),
                    revoked_at=revoked_at,
                    is_expired=expires_at <= calculated_at,
                    is_revoked=revoked_at is not None,
                )
            )
        return EndpointDetailDto(**base, certificates=certificates)


class AlertService:
    def __init__(
        self,
        repository: AlertRepository,
        *,
        event_service: EventService,
        rules: list[LoadedRule],
    ) -> None:
        self.repository = repository
        self.event_service = event_service
        self.rules = {(item.rule.rule_code, item.rule.version): item for item in rules}

    def list(self, query: AlertListQuery, *, from_: datetime, to: datetime) -> PagedData[AlertDto]:
        filters = dict(
            from_=from_,
            to=to,
            endpoint_id=query.endpoint_id,
            status=query.status,
            severity=query.severity.value if query.severity else None,
            rule_code=query.rule_code,
        )
        rows = self.repository.list_rows(
            **filters,
            sort_by=query.sort_by,
            sort_order=query.sort_order,
            limit=query.size,
            offset=(query.page - 1) * query.size,
        )
        total = self.repository.count_rows(**filters)
        return PagedData(
            items=[alert_dto(row) for row in rows],
            page=query.page,
            size=query.size,
            total=total,
        )

    def detail(self, alert_id: int) -> AlertDetailDto:
        row = self.repository.detail(alert_id)
        if row is None:
            raise ApplicationError(404, "NOT_FOUND", "Alert was not found.")
        source_event = None
        try:
            detail = self.event_service.detail(
                event_id=UUID(str(row["event_id"])),
                endpoint_id=int(row["endpoint_id"]),
                occurred_at=_timestamp(row["event_occurred_at"]),
            )
            if detail is not None:
                source_event = detail.model_dump(exclude={"raw_payload", "payload_sha256", "schema_version"})
        except ApplicationError as error:
            if error.code != "ARCHIVE_NOT_READY":
                raise
            source_event = None
        incidents = [
            IncidentReferenceDto.model_validate(item) for item in self.repository.incidents_for_alert(alert_id)
        ]
        loaded = self.rules.get((str(row["rule_code"]), int(row["rule_version"])))
        guidance = (
            []
            if loaded is None
            else [
                ResponseGuidanceStepDto.model_validate(item.model_dump())
                for item in sorted(loaded.rule.response_guidance, key=lambda item: item.order)
            ]
        )
        return AlertDetailDto(
            **alert_dto(row).model_dump(),
            source_event=source_event,
            incidents=incidents,
            response_guidance=guidance,
        )

    def update_status(
        self,
        alert_id: int,
        *,
        status,
        actor_identifier: str,
        request_id: str,
        changed_at: datetime,
    ) -> AlertDto:
        try:
            row = self.repository.update_status_with_audit(
                alert_id=alert_id,
                status=status,
                actor_identifier=actor_identifier,
                request_id=request_id,
                changed_at=changed_at,
            )
        except KeyError as error:
            raise ApplicationError(404, "NOT_FOUND", "Alert was not found.") from error
        return alert_dto(row)


class IncidentService:
    def __init__(self, repository: IncidentRepository) -> None:
        self.repository = repository

    def list(self, query: IncidentListQuery, *, from_: datetime, to: datetime) -> PagedData[IncidentDto]:
        filters = dict(
            from_=from_,
            to=to,
            endpoint_id=query.endpoint_id,
            status=query.status,
            severity=query.severity.value if query.severity else None,
        )
        rows = self.repository.list_rows(
            **filters,
            sort_order=query.sort_order,
            limit=query.size,
            offset=(query.page - 1) * query.size,
        )
        total = self.repository.count_rows(**filters)
        return PagedData(
            items=[incident_dto(row) for row in rows],
            page=query.page,
            size=query.size,
            total=total,
        )

    def detail(self, incident_id: int) -> IncidentDetailDto:
        row = self.repository.detail(incident_id)
        if row is None:
            raise ApplicationError(404, "NOT_FOUND", "Incident was not found.")
        return IncidentDetailDto(
            **incident_dto(row).model_dump(),
            alerts=[alert_dto(item) for item in self.repository.alerts_for_incident(incident_id)],
        )


def endpoint_dto(row: dict[str, Any], *, calculated_at: datetime) -> EndpointDto:
    alerts = [
        AlertRiskInput(
            alert_id=int(item["alert_id"]),
            rule_code=str(item["rule_code"]),
            rule_version=int(item["rule_version"]),
            risk_score=Decimal(str(item["risk_score"])),
            detected_at=_timestamp(item["detected_at"]),
            title=str(item["title"]),
        )
        for item in row["active_alerts"]
    ]
    incidents = [
        IncidentRiskInput(
            incident_id=int(item["incident_id"]),
            title=str(item["title"]),
            severity=Severity(item["severity"]),
            last_detected_at=_timestamp(item["last_detected_at"]),
        )
        for item in row["open_incidents"]
    ]
    risk = calculate_endpoint_risk(alerts, incidents, calculated_at=calculated_at)
    risk_dto = EndpointRiskDto.model_validate(
        {
            "score": risk.score,
            "level": risk.level,
            "active_alert_count": row.get("active_alert_count", risk.active_alert_count),
            "open_incident_count": row.get("open_incident_count", risk.open_incident_count),
            "highest_alert_risk_score": row.get("highest_alert_risk_score", risk.highest_alert_risk_score),
            "calculated_at": risk.calculated_at,
            "risk_factors": [
                {
                    "code": factor.code,
                    "title": factor.title,
                    "description": factor.description,
                    "contribution": factor.contribution,
                    "source_type": factor.source_type,
                    "source_id": factor.source_id,
                }
                for factor in risk.risk_factors
            ],
        }
    )
    last_seen_at = _timestamp(row["last_seen_at"]) if row["last_seen_at"] else None
    sensors = [
        SensorHealthDto(
            sensor=item["sensor"],
            status=item["status"],
            provider=item.get("provider"),
            packet_drop_count=item.get("packetDropCount"),
            parse_error_count=item.get("parseErrorCount"),
        )
        for item in row["sensor_health_json"]
    ]
    return EndpointDto(
        endpoint_id=row["endpoint_id"],
        agent_id=row["agent_id"],
        hostname=row["hostname"],
        os_type=row["os_type"],
        os_version=row["os_version"],
        ip_address=str(row["ip_address"]) if row["ip_address"] is not None else None,
        agent_version=row["agent_version"],
        agent_build_id=row["agent_build_id"],
        agent_arch=row["agent_arch"],
        capability_codes=list(row["capability_codes_json"]),
        status=row["status"],
        last_seen_at=last_seen_at,
        is_stale=last_seen_at is not None and last_seen_at < calculated_at - timedelta(days=7),
        sensor_health=sensors,
        risk=risk_dto,
        registered_at=_timestamp(row["registered_at"]),
    )


def alert_dto(row: dict[str, Any]) -> AlertDto:
    values = {field: row.get(field) for field in AlertDto.model_fields}
    values["event_id"] = str(values["event_id"])
    values["batch_id"] = str(values["batch_id"]) if values["batch_id"] is not None else None
    return AlertDto.model_validate(values)


def incident_dto(row: dict[str, Any]) -> IncidentDto:
    return IncidentDto.model_validate({field: row.get(field) for field in IncidentDto.model_fields})


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
