from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID

from .api_services import endpoint_dto
from .contracts.common import PagedData
from .contracts.dashboard import TimeRangeDto
from .contracts.enums import (
    EventType,
    InvestigationEvidence,
    InvestigationNodeType,
    InvestigationRelation,
    InvestigationWarningCode,
    Severity,
)
from .contracts.events import ProcessTreeDto, ProcessTreeNodeDto
from .contracts.investigations import (
    AttackTimelineDto,
    AttackTimelineItemDto,
    EgressTopologyDto,
    EventFailureDto,
    IncidentInvestigationDto,
    InvestigationEdgeDto,
    InvestigationFallbackDto,
    InvestigationNodeDto,
    InvestigationWarningDto,
    TopologyEdgeDto,
    TopologyNodeDto,
)
from .contracts.requests import EventListQuery, FailureListQuery
from .errors import ApplicationError
from .event_service import EventService
from .storage.clickhouse import FailureRepository
from .storage.postgres import AlertRepository, EndpointRepository, IncidentRepository

MAX_INVESTIGATION_NODES = 250
MAX_INVESTIGATION_EDGES = 500
MAX_INVESTIGATION_ALERTS = 250
MAX_PROCESS_TREE_EVENTS = 10_000
MAX_TOPOLOGY_EVENTS = 10_000
MAX_TIMELINE_ALERTS = 5_000

_NODE_TYPE_ORDER = {
    InvestigationNodeType.INCIDENT: 0,
    InvestigationNodeType.ALERT: 1,
    InvestigationNodeType.EVENT: 2,
    InvestigationNodeType.PROCESS: 3,
    InvestigationNodeType.DESTINATION: 4,
}
_RELATION_ORDER = {
    InvestigationRelation.CONTAINS: 0,
    InvestigationRelation.TRIGGERED_BY: 1,
    InvestigationRelation.PARENT_OF: 2,
    InvestigationRelation.CONNECTED_TO: 3,
}


class FailureService:
    def __init__(self, repository: FailureRepository) -> None:
        self.repository = repository

    def list(self, query: FailureListQuery, *, from_: datetime, to: datetime) -> PagedData[EventFailureDto]:
        filters = dict(
            from_=from_,
            to=to,
            status=query.status.value if query.status else None,
            failure_stage=query.failure_stage,
            retryable=query.retryable,
        )
        rows = self.repository.current_rows(
            **filters,
            sort_order=query.sort_order,
            limit=query.size,
            offset=(query.page - 1) * query.size,
        )
        total = self.repository.count_current(**filters)
        return PagedData(
            items=[_failure_dto(row) for row in rows],
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
            max_items=MAX_PROCESS_TREE_EVENTS,
            overflow_label="Process tree",
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
        alerts = self.incidents.alerts_for_incident(incident_id, limit=MAX_TIMELINE_ALERTS + 1)
        if len(alerts) > MAX_TIMELINE_ALERTS:
            raise ApplicationError(
                400,
                "VALIDATION_ERROR",
                f"Incident timeline contains more than {MAX_TIMELINE_ALERTS} alerts.",
            )
        event_rows, _unavailable = self._alert_events(alerts, default_endpoint_id=endpoint_id)
        for alert in alerts:
            event = event_rows.get(str(alert["event_id"]))
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

    def investigation(self, incident_id: int) -> IncidentInvestigationDto:
        incident = self.incidents.detail(incident_id)
        if incident is None:
            raise ApplicationError(404, "NOT_FOUND", "Incident was not found.")

        endpoint_id = int(incident["endpoint_id"])
        incident_node_id = f"incident:{incident_id}"
        nodes: dict[str, InvestigationNodeDto] = {}
        edges: dict[str, InvestigationEdgeDto] = {}
        warnings: dict[tuple[InvestigationWarningCode, str], InvestigationWarningDto] = {}

        def add_node(node: InvestigationNodeDto) -> None:
            existing = nodes.get(node.node_id)
            if existing is None:
                nodes[node.node_id] = node
            elif (
                node.node_type is InvestigationNodeType.PROCESS
                and existing.process_name is None
                and node.process_name is not None
            ):
                nodes[node.node_id] = node

        def add_edge(edge: InvestigationEdgeDto) -> None:
            edges.setdefault(edge.edge_id, edge)

        add_node(
            _investigation_node(
                node_id=incident_node_id,
                node_type=InvestigationNodeType.INCIDENT,
                label=str(incident["title"]),
                endpoint_id=endpoint_id,
                incident_id=incident_id,
                occurred_at=_utc_timestamp(incident["first_detected_at"]),
                severity=Severity(str(incident["severity"])),
            )
        )

        fetched_alert_rows = self.incidents.alerts_for_incident(incident_id, limit=MAX_INVESTIGATION_ALERTS + 1)
        alerts_truncated = len(fetched_alert_rows) > MAX_INVESTIGATION_ALERTS
        alert_rows = sorted(
            fetched_alert_rows[:MAX_INVESTIGATION_ALERTS],
            key=lambda row: (_utc_timestamp(row["event_occurred_at"]), int(row["alert_id"])),
        )
        event_rows, unavailable_event_ids = self._alert_events(alert_rows, default_endpoint_id=endpoint_id)
        archive_not_ready = bool(unavailable_event_ids)
        for alert in alert_rows:
            alert_id = int(alert["alert_id"])
            alert_endpoint_id = int(alert["endpoint_id"])
            event_id = str(alert["event_id"])
            event_occurred_at = _utc_timestamp(alert["event_occurred_at"])
            alert_node_id = f"alert:{alert_id}"
            add_node(
                _investigation_node(
                    node_id=alert_node_id,
                    node_type=InvestigationNodeType.ALERT,
                    label=str(alert["title"]),
                    endpoint_id=alert_endpoint_id,
                    incident_id=incident_id,
                    alert_id=alert_id,
                    event_id=event_id,
                    occurred_at=_utc_timestamp(alert["detected_at"]),
                    severity=Severity(str(alert["severity"])),
                    risk_score=float(alert["risk_score"]),
                )
            )
            add_edge(
                _investigation_edge(
                    edge_id=f"contains:{incident_id}:{alert_id}",
                    source_node_id=incident_node_id,
                    target_node_id=alert_node_id,
                    relation=InvestigationRelation.CONTAINS,
                    incident_id=incident_id,
                    alert_id=alert_id,
                    event_id=event_id,
                    observed_at=_utc_timestamp(alert["detected_at"]),
                )
            )

            event = event_rows.get(event_id)
            if event_id in unavailable_event_ids:
                warning_code = InvestigationWarningCode.ARCHIVE_NOT_READY
                warning_message = "Event evidence is in an archive bucket that is not ready."
            else:
                warning_code = InvestigationWarningCode.EVENT_NOT_FOUND
                warning_message = "Event evidence is not present in HOT or RESTORED storage."

            if event is None:
                warning_key = (warning_code, event_id)
                warnings.setdefault(
                    warning_key,
                    InvestigationWarningDto(
                        code=warning_code,
                        message=warning_message,
                        event_id=event_id,
                        endpoint_id=alert_endpoint_id,
                        occurred_at=event_occurred_at,
                    ),
                )
                continue

            event_node_id = f"event:{event_id}"
            add_node(
                _investigation_node(
                    node_id=event_node_id,
                    node_type=InvestigationNodeType.EVENT,
                    label=_event_label(event),
                    endpoint_id=alert_endpoint_id,
                    incident_id=incident_id,
                    alert_id=alert_id,
                    event_id=event_id,
                    pid=event.pid,
                    process_name=event.process_name,
                    destination=_event_destination(event),
                    protocol=_event_protocol(event),
                    occurred_at=event.occurred_at,
                    event_type=event.event_type,
                )
            )
            add_edge(
                _investigation_edge(
                    edge_id=f"triggered-by-alert:{alert_id}:{event_id}",
                    source_node_id=alert_node_id,
                    target_node_id=event_node_id,
                    relation=InvestigationRelation.TRIGGERED_BY,
                    incident_id=incident_id,
                    alert_id=alert_id,
                    event_id=event_id,
                    observed_at=event.occurred_at,
                )
            )

            process_node_id = _process_node_id(alert_endpoint_id, event_id, event.pid, event.process_name)
            if process_node_id is None:
                continue
            add_node(
                _investigation_node(
                    node_id=process_node_id,
                    node_type=InvestigationNodeType.PROCESS,
                    label=event.process_name or f"PID {event.pid}",
                    endpoint_id=alert_endpoint_id,
                    incident_id=incident_id,
                    alert_id=alert_id,
                    event_id=event_id,
                    pid=event.pid,
                    process_name=event.process_name,
                    occurred_at=event.occurred_at,
                )
            )
            add_edge(
                _investigation_edge(
                    edge_id=f"triggered-by-event:{event_id}:{process_node_id}",
                    source_node_id=event_node_id,
                    target_node_id=process_node_id,
                    relation=InvestigationRelation.TRIGGERED_BY,
                    incident_id=incident_id,
                    alert_id=alert_id,
                    event_id=event_id,
                    observed_at=event.occurred_at,
                )
            )

            if event.pid is not None and event.ppid is not None:
                parent_node_id = f"process:{alert_endpoint_id}:{event.ppid}"
                add_node(
                    _investigation_node(
                        node_id=parent_node_id,
                        node_type=InvestigationNodeType.PROCESS,
                        label=f"PID {event.ppid}",
                        endpoint_id=alert_endpoint_id,
                        incident_id=incident_id,
                        alert_id=alert_id,
                        event_id=event_id,
                        pid=event.ppid,
                        occurred_at=event.occurred_at,
                    )
                )
                add_edge(
                    _investigation_edge(
                        edge_id=f"parent-of:{event_id}:{parent_node_id}:{process_node_id}",
                        source_node_id=parent_node_id,
                        target_node_id=process_node_id,
                        relation=InvestigationRelation.PARENT_OF,
                        incident_id=incident_id,
                        alert_id=alert_id,
                        event_id=event_id,
                        observed_at=event.occurred_at,
                    )
                )

            destination = _event_destination(event)
            if destination is None:
                continue
            protocol = _event_protocol(event)
            destination_key = f"{alert_endpoint_id}\0{protocol}\0{destination}".encode()
            destination_node_id = f"destination:{alert_endpoint_id}:{sha256(destination_key).hexdigest()[:16]}"
            add_node(
                _investigation_node(
                    node_id=destination_node_id,
                    node_type=InvestigationNodeType.DESTINATION,
                    label=destination,
                    endpoint_id=alert_endpoint_id,
                    incident_id=incident_id,
                    alert_id=alert_id,
                    event_id=event_id,
                    destination=destination,
                    protocol=protocol,
                    occurred_at=event.occurred_at,
                )
            )
            add_edge(
                _investigation_edge(
                    edge_id=f"connected-to:{event_id}:{process_node_id}:{destination_node_id}",
                    source_node_id=process_node_id,
                    target_node_id=destination_node_id,
                    relation=InvestigationRelation.CONNECTED_TO,
                    incident_id=incident_id,
                    alert_id=alert_id,
                    event_id=event_id,
                    observed_at=event.occurred_at,
                )
            )

        ordered_nodes = sorted(
            nodes.values(),
            key=lambda node: (_NODE_TYPE_ORDER[node.node_type], _sortable_time(node.occurred_at), node.node_id),
        )
        ordered_edges = sorted(
            edges.values(),
            key=lambda edge: (_RELATION_ORDER[edge.relation], _sortable_time(edge.observed_at), edge.edge_id),
        )
        returned_nodes = ordered_nodes[:MAX_INVESTIGATION_NODES]
        returned_node_ids = {node.node_id for node in returned_nodes}
        reference_safe_edges = [
            edge
            for edge in ordered_edges
            if edge.source_node_id in returned_node_ids and edge.target_node_id in returned_node_ids
        ]
        returned_edges = reference_safe_edges[:MAX_INVESTIGATION_EDGES]
        truncated = (
            alerts_truncated
            or len(returned_nodes) < len(ordered_nodes)
            or len(returned_edges) < len(ordered_edges)
        )
        ordered_warnings = sorted(warnings.values(), key=lambda item: (item.code.value, item.event_id or ""))

        return IncidentInvestigationDto(
            incident_id=incident_id,
            time_range=TimeRangeDto(
                from_=_utc_timestamp(incident["window_start_at"]),
                to=_utc_timestamp(incident["window_end_at"]),
            ),
            nodes=returned_nodes,
            edges=returned_edges,
            node_count=len(returned_nodes),
            edge_count=len(returned_edges),
            truncated=truncated,
            partial=bool(ordered_warnings),
            warnings=ordered_warnings,
            fallback=InvestigationFallbackDto(
                timeline_available=True,
                alert_table_available=True,
                event_table_available=not archive_not_ready,
            ),
        )

    def topology(
        self,
        *,
        from_: datetime,
        to: datetime,
        endpoint_ids: list[int] | None,
        calculated_at: datetime,
    ) -> EgressTopologyDto:
        endpoint_filter = set(endpoint_ids or [])
        if endpoint_filter:
            events = []
            for endpoint_id in sorted(endpoint_filter):
                events.extend(
                    self._event_items(
                        endpoint_id=endpoint_id,
                        from_=from_,
                        to=to,
                        max_items=MAX_TOPOLOGY_EVENTS - len(events),
                    )
                )
        else:
            events = self._event_items(
                endpoint_id=None,
                from_=from_,
                to=to,
                max_items=MAX_TOPOLOGY_EVENTS,
            )
        event_ids = [str(event.event_id) for event in events]
        counts_by_event = getattr(self.alerts, "counts_by_event_ids", None)
        if callable(counts_by_event):
            alert_counts = Counter(counts_by_event(event_ids, from_=from_, to=to))
        else:
            alert_rows = self.alerts.list_rows(from_=from_, to=to)
            alert_counts = Counter(
                str(row["event_id"])
                for row in alert_rows
                if str(row["event_id"]) in event_ids
                and (not endpoint_filter or int(row["endpoint_id"]) in endpoint_filter)
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
        max_items: int | None = None,
        overflow_label: str = "Topology",
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
        if max_items is not None and total > max_items:
            raise ApplicationError(
                400,
                "VALIDATION_ERROR",
                (
                    f"{overflow_label} range contains more than {max_items} events; "
                    "narrow the time range or Endpoint filter."
                ),
            )
        page = 2
        while len(items) < total:
            page_items, _ = self.events.list_rows(query.model_copy(update={"page": page}), from_=from_, to=to)
            if not page_items:
                break
            items.extend(page_items)
            page += 1
        return items

    def _alert_events(
        self,
        alert_rows: list[dict[str, Any]],
        *,
        default_endpoint_id: int,
    ) -> tuple[dict[str, Any], set[str]]:
        identities = [
            (
                UUID(str(alert["event_id"])),
                int(alert.get("endpoint_id", default_endpoint_id)),
                _utc_timestamp(alert["event_occurred_at"]),
            )
            for alert in alert_rows
        ]
        bulk = getattr(self.events, "details_bulk", None)
        if callable(bulk):
            return bulk(identities)
        found: dict[str, Any] = {}
        unavailable: set[str] = set()
        for event_id, endpoint_id, occurred_at in identities:
            try:
                event = self.events.detail(
                    event_id=event_id,
                    endpoint_id=endpoint_id,
                    occurred_at=occurred_at,
                )
            except ApplicationError as error:
                if error.code != "ARCHIVE_NOT_READY":
                    raise
                unavailable.add(str(event_id))
                continue
            if event is not None:
                found[str(event_id)] = event
        return found, unavailable


def _investigation_node(
    *,
    node_id: str,
    node_type: InvestigationNodeType,
    label: str,
    endpoint_id: int | None = None,
    incident_id: int | None = None,
    alert_id: int | None = None,
    event_id: str | None = None,
    pid: int | None = None,
    process_name: str | None = None,
    destination: str | None = None,
    protocol: str | None = None,
    occurred_at: datetime | None = None,
    severity: Severity | None = None,
    event_type: EventType | None = None,
    risk_score: float | None = None,
) -> InvestigationNodeDto:
    return InvestigationNodeDto(
        node_id=node_id,
        node_type=node_type,
        label=label,
        endpoint_id=endpoint_id,
        incident_id=incident_id,
        alert_id=alert_id,
        event_id=event_id,
        pid=pid,
        process_name=process_name,
        destination=destination,
        protocol=protocol,
        occurred_at=occurred_at,
        severity=severity,
        event_type=event_type,
        risk_score=risk_score,
    )


def _investigation_edge(
    *,
    edge_id: str,
    source_node_id: str,
    target_node_id: str,
    relation: InvestigationRelation,
    incident_id: int | None,
    alert_id: int | None,
    event_id: str | None,
    observed_at: datetime | None,
) -> InvestigationEdgeDto:
    return InvestigationEdgeDto(
        edge_id=edge_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relation=relation,
        evidence=InvestigationEvidence.OBSERVED,
        incident_id=incident_id,
        alert_id=alert_id,
        event_id=event_id,
        observed_at=observed_at,
    )


def _process_node_id(endpoint_id: int, event_id: str, pid: int | None, process_name: str | None) -> str | None:
    if pid is not None:
        return f"process:{endpoint_id}:{pid}"
    if process_name:
        return f"process:{endpoint_id}:event:{event_id}"
    return None


def _event_destination(event: Any) -> str | None:
    return event.remote_domain or event.http_host or event.tls_sni or event.remote_ip or event.dns_query


def _event_protocol(event: Any) -> str | None:
    if _event_destination(event) is None:
        return None
    return event.l7_protocol or event.protocol or ("DNS" if event.dns_query else "UNKNOWN")


def _event_label(event: Any) -> str:
    return event.process_name or _event_destination(event) or event.file_path or event.event_type.value


def _utc_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _sortable_time(value: datetime | None) -> datetime:
    return value or datetime.min.replace(tzinfo=UTC)


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
