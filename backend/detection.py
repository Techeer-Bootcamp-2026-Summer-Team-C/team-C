import ipaddress
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from .rule_loader import LoadedRule
from .storage.models import AlertInsert


@dataclass(frozen=True, slots=True)
class IncidentCorrelation:
    endpoint_id: int
    correlation_key: str
    window_start_at: datetime
    window_end_at: datetime


@dataclass(frozen=True, slots=True)
class DetectionMatch:
    alert: AlertInsert
    incident: IncidentCorrelation | None


def _matches_operator(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "eq":
        return actual == expected
    if operator == "neq":
        return actual != expected
    if operator == "contains":
        return actual is not None and str(expected) in str(actual)
    if operator == "regex":
        return actual is not None and re.search(str(expected), str(actual)) is not None
    if operator == "in":
        return isinstance(expected, list) and actual in expected
    if operator == "cidr_contains":
        try:
            return ipaddress.ip_address(str(actual)) in ipaddress.ip_network(str(expected), strict=False)
        except ValueError:
            return False
    if operator == "gt":
        return actual is not None and actual > expected
    if operator == "gte":
        return actual is not None and actual >= expected
    if operator == "lt":
        return actual is not None and actual < expected
    if operator == "lte":
        return actual is not None and actual <= expected
    return False


def _window(occurred_at: datetime, window_seconds: int) -> tuple[datetime, datetime]:
    normalized = occurred_at.astimezone(UTC)
    start_epoch = (int(normalized.timestamp()) // window_seconds) * window_seconds
    start = datetime.fromtimestamp(start_epoch, tz=UTC)
    return start, start + timedelta(seconds=window_seconds)


class DetectionEngine:
    def __init__(self, rules: list[LoadedRule]) -> None:
        self.rules = tuple(item for item in rules if item.rule.enabled)

    def evaluate(self, event: dict[str, Any], *, detected_at: datetime) -> list[DetectionMatch]:
        matches: list[DetectionMatch] = []
        for loaded in self.rules:
            rule = loaded.rule
            event_type = event.get("event_type")
            if getattr(event_type, "value", event_type) != rule.event_type.value:
                continue
            if not all(
                _matches_operator(event.get(condition.field), condition.operator, condition.value)
                for condition in rule.conditions.all
            ):
                continue
            if rule.mitre is None or loaded.tactic_name is None or loaded.technique_name is None:
                raise RuntimeError("enabled rule was not readiness-validated")
            event_id = UUID(str(event["event_id"]))
            batch_value = event.get("batch_id")
            alert = AlertInsert(
                endpoint_id=int(event["endpoint_id"]),
                event_id=event_id,
                event_occurred_at=event["occurred_at"],
                batch_id=UUID(str(batch_value)) if batch_value is not None else None,
                agent_id=str(event["agent_id"]),
                rule_code=rule.rule_code,
                rule_name=rule.rule_name,
                rule_version=rule.version,
                mitre_tactic_code=rule.mitre.tactic_code,
                mitre_tactic_name=loaded.tactic_name,
                mitre_technique_code=rule.mitre.technique_code,
                mitre_technique_name=loaded.technique_name,
                title=rule.alert_title,
                summary=rule.alert_summary,
                severity=rule.severity,
                risk_score=Decimal(str(rule.risk_score)),
                detected_at=detected_at,
            )
            correlation = None
            if rule.incident.enabled:
                if rule.incident.correlation_key is None or rule.incident.window_seconds is None:
                    raise RuntimeError("enabled incident was not readiness-validated")
                start, end = _window(event["occurred_at"], rule.incident.window_seconds)
                correlation = IncidentCorrelation(
                    endpoint_id=int(event["endpoint_id"]),
                    correlation_key=rule.incident.correlation_key,
                    window_start_at=start,
                    window_end_at=end,
                )
            matches.append(DetectionMatch(alert, correlation))
        return matches
