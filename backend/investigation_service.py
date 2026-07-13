from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from .api_services import endpoint_dto
from .contracts.common import PagedData
from .contracts.enums import EventType, Severity
from .contracts.events import ProcessTreeDto, ProcessTreeNodeDto
from .contracts.investigations import (
    AttackTimelineDto,
    AttackTimelineItemDto,
    EgressTopologyDto,
    EventFailureDto,
    TopologyEdgeDto,
    TopologyNodeDto,
)
from .contracts.requests import EventListQuery, FailureListQuery
from .errors import ApplicationError
from .event_service import EventService
from .storage.clickhouse import FailureRepository
from .storage.postgres import AlertRepository, EndpointRepository, IncidentRepository


class FailureService:
    def __init__(self, repository: FailureRepository) -> None:
        self.repository = repository

    def list(self, query: FailureListQuery, *, from_: datetime, to: datetime) -> PagedData[EventFailureDto]:
        rows = self.repository.current_rows(
            from_=from_,
            to=to,
            status=query.status.value if query.status else None,
            failure_stage=query.failure_stage,
            retryable=query.retryable,
            sort_order=query.sort_order,
        )
        total = len(rows)
        start = (query.page - 1) * query.size
        return PagedData(
            items=[_failure_dto(row) for row in rows[start : start + query.size]],
            page=query.page,
            size=query.size,
            total=total,
        )


class InvestigationService:
    def __init__(
        self,
        *,
        endpoints: EndpointRepository,
        alerts: AlertRepository,
        incidents: IncidentRepository,
        events: EventService,
    ) -> None:
        self.endpoints = endpoints
        self.alerts = alerts
        self.incidents = incidents
        self.events = events

    def process_tree(
        self,
        endpoint_id: int,
        *,
        from_: datetime,
        to: datetime,
        selected_pid: int | None,
    ) -> ProcessTreeDto:
        events = self._event_items(
            endpoint_id=endpoint_id,
            from_=from_,
            to=to,
            event_type=EventType.PROCESS_EXECUTION,
        )
        grouped: dict[int, list[Any]] = {}
        for event in events:
            if event.pid is not None:
                grouped.setdefault(event.pid, []).append(event)
        captured = set(grouped)
        nodes = []
        for pid, rows in grouped.items():
            rows.sort(key=lambda item: item.occurred_at)
            latest = rows[-1]
            nodes.append(
                ProcessTreeNodeDto(
                    pid=pid,
                    ppid=latest.ppid,
                    process_name=latest.process_name or f"PID {pid}",
                    process_path=latest.process_path,
                    command_line=latest.command_line,
                    user_name=latest.user_name,
                    first_seen_at=rows[0].occurred_at,
                    last_seen_at=latest.occurred_at,
                    event_count=len(rows),
                    selected=pid == selected_pid,
                    parent_captured=latest.ppid is not None and latest.ppid in captured,
                )
            )
        nodes.sort(key=lambda item: (item.first_seen_at, item.pid))
        return ProcessTreeDto(endpoint_id=endpoint_id, from_=from_, to=to, nodes=nodes)

    def timeline(self, incident_id: int) -> AttackTimelineDto:
        incident = self.incidents.detail(incident_id)
        if incident is None:
            raise ApplicationError(404, "NOT_FOUND", "Incident was not found.")
        endpoint_id = int(incident["endpoint_id"])
        items = [
            AttackTimelineItemDto(
                item_type="INCIDENT",
                occurred_at=incident["first_detected_at"],
                endpoint_id=endpoint_id,
                title=str(incident["title"]),
                summary=str(incident["description"] or "Incident correlation window opened."),
                severity=Severity(str(incident["severity"])),
                event_type=None,
                event_id=None,
                alert_id=None,
                incident_id=incident_id,
            )
        ]
        for alert in self.incidents.alerts_for_incident(incident_id):
            event = None
            try:
                event = self.events.detail(
                    event_id=UUID(str(alert["event_id"])),
                    endpoint_id=endpoint_id,
                    occurred_at=alert["event_occurred_at"],
                )
            except ApplicationError:
                event = None
            if event is not None:
                items.append(
                    AttackTimelineItemDto(
                        item_type="EVENT",
                        occurred_at=event.occurred_at,
                        endpoint_id=endpoint_id,
                        title=event.process_name or event.remote_domain or event.file_path or event.event_type.value,
                        summary=_event_summary(event),
                        severity=None,
                        event_type=event.event_type,
                        event_id=event.event_id,
                        alert_id=None,
                        incident_id=incident_id,
                    )
                )
            items.append(
                AttackTimelineItemDto(
                    item_type="ALERT",
                    occurred_at=alert["detected_at"],
                    endpoint_id=endpoint_id,
                    title=str(alert["title"]),
                    summary=str(alert["summary"]),
                    severity=Severity(str(alert["severity"])),
                    event_type=None,
                    event_id=str(alert["event_id"]),
                    alert_id=int(alert["alert_id"]),
                    incident_id=incident_id,
                )
            )
        items.sort(key=lambda item: (item.occurred_at, item.item_type, item.alert_id or 0))
        return AttackTimelineDto(incident_id=incident_id, endpoint_id=endpoint_id, items=items)

    def topology(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_ids: list[int] | None,
        calculated_at: datetime,
    ) -> EgressTopologyDto:
        events = self._event_items(endpoint_id=None, from_=from_, to=to)
        endpoint_filter = set(endpoint_ids or [])
        if endpoint_filter:
            events = [event for event in events if event.endpoint_id in endpoint_filter]
        alert_rows = self.alerts.list_rows(from_=from_, to=to)
        alert_counts = Counter(
            str(row["event_id"])
            for row in alert_rows
            if not endpoint_filter or int(row["endpoint_id"]) in endpoint_filter
        )
        grouped: dict[tuple[int, str, str], dict[str, Any]] = {}
        for event in events:
            target = event.remote_domain or event.http_host or event.tls_sni or event.remote_ip or event.dns_query
            if not target:
                continue
            protocol = event.l7_protocol or event.protocol or ("DNS" if event.dns_query else "UNKNOWN")
            key = (event.endpoint_id, target, protocol)
            row = grouped.setdefault(
                key,
                {"source_label": event.hostname, "event_count": 0, "alert_count": 0, "last_seen_at": event.occurred_at},
            )
            row["event_count"] += 1
            row["alert_count"] += alert_counts[str(event.event_id)]
            row["last_seen_at"] = max(row["last_seen_at"], event.occurred_at)
        edge_endpoint_ids = {key[0] for key in grouped}
        selected_ids = endpoint_filter or edge_endpoint_ids
        endpoint_rows = self.endpoints.risk_snapshot(endpoint_ids=sorted(selected_ids) if selected_ids else None)
        endpoint_items = [endpoint_dto(row, calculated_at=calculated_at) for row in endpoint_rows]
        nodes = [
            TopologyNodeDto(
                endpoint_id=item.endpoint_id,
                hostname=item.hostname,
                status=item.status,
                risk_score=item.risk.score,
                risk_level=item.risk.level,
                alert_count=item.risk.active_alert_count,
            )
            for item in endpoint_items
            if not selected_ids or item.endpoint_id in selected_ids
        ]
        labels = {node.endpoint_id: node.hostname for node in nodes}
        edges = [
            TopologyEdgeDto(
                endpoint_id=endpoint_id,
                source_label=labels.get(endpoint_id, str(row["source_label"])),
                target=target,
                protocol=protocol,
                event_count=int(row["event_count"]),
                alert_count=int(row["alert_count"]),
                last_seen_at=row["last_seen_at"],
            )
            for (endpoint_id, target, protocol), row in grouped.items()
        ]
        edges.sort(key=lambda item: (-item.alert_count, -item.event_count, item.endpoint_id, item.target))
        return EgressTopologyDto(from_=from_, to=to, nodes=nodes, edges=edges)

    def _event_items(
        self,
        *,
        endpoint_id: int | None,
        from_: datetime,
        to: datetime,
        event_type: EventType | None = None,
    ):
        values: dict[str, Any] = {
            "timePreset": "CUSTOM",
            "from": from_,
            "to": to,
            "page": 1,
            "size": 500,
            "sortOrder": "asc",
        }
        if endpoint_id is not None:
            values["endpointId"] = endpoint_id
        if event_type is not None:
            values["eventType"] = event_type.value
        query = EventListQuery.model_validate(values)
        items, total = self.events.list_rows(query, from_=from_, to=to)
        page = 2
        while len(items) < total:
            page_items, _ = self.events.list_rows(query.model_copy(update={"page": page}), from_=from_, to=to)
            items.extend(page_items)
            page += 1
        return items


def _event_summary(event) -> str:
    values = [
        event.command_line,
        event.file_path,
        event.remote_domain or event.remote_ip,
        event.dns_query,
        event.http_host,
    ]
    return " | ".join(str(value) for value in values if value) or f"{event.event_type.value} observed"


def _failure_dto(row: dict[str, Any]) -> EventFailureDto:
    values = dict(row)
    values["failure_id"] = str(values["failure_id"])
    values["event_id"] = str(values["event_id"])
    payload_sha256 = values.get("payload_sha256")
    if isinstance(payload_sha256, bytes):
        values["payload_sha256"] = payload_sha256.decode("ascii")
    for field in (
        "failed_at",
        "last_replayed_at",
        "resolved_at",
        "retention_expires_at",
        "created_at",
        "updated_at",
    ):
        value = values.get(field)
        if value is not None and value.tzinfo is None:
            values[field] = value.replace(tzinfo=UTC)
    return EventFailureDto.model_validate(values)
