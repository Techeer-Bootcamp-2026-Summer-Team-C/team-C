from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.contracts.dashboard_layouts import DashboardLayoutPutRequest
from backend.contracts.enums import AlertSortBy, InvestigationEvidence
from backend.contracts.investigations import IncidentInvestigationDto
from backend.contracts.requests import AlertListQuery, EndpointListQuery


def test_endpoint_search_query_is_trimmed_and_bounded() -> None:
    assert EndpointListQuery.model_validate({"q": "  SOC-WIN  "}).q == "SOC-WIN"
    with pytest.raises(ValidationError):
        EndpointListQuery.model_validate({"q": " "})
    with pytest.raises(ValidationError):
        EndpointListQuery.model_validate({"q": "x" * 129})


def test_alert_sort_contract_defaults_to_priority_and_rejects_unknown_fields() -> None:
    assert AlertListQuery().sort_by is AlertSortBy.PRIORITY
    assert AlertListQuery.model_validate({"sortBy": "detectedAt"}).sort_by is AlertSortBy.DETECTED_AT
    with pytest.raises(ValidationError):
        AlertListQuery.model_validate({"sortBy": "title"})


def test_layout_contract_accepts_only_versions_one_and_two() -> None:
    values = {"revision": 0, "widgets": []}
    assert DashboardLayoutPutRequest(layout_version=1, **values).layout_version == 1
    assert DashboardLayoutPutRequest(layout_version=2, **values).layout_version == 2
    with pytest.raises(ValidationError):
        DashboardLayoutPutRequest(layout_version=3, **values)


def test_investigation_contract_keeps_nullable_keys_and_empty_collections() -> None:
    occurred_at = datetime(2026, 7, 15, tzinfo=UTC)
    model = IncidentInvestigationDto.model_validate(
        {
            "incidentId": 1,
            "timeRange": {"from": occurred_at, "to": occurred_at.replace(hour=1)},
            "nodes": [
                {
                    "nodeId": "incident:1",
                    "nodeType": "INCIDENT",
                    "label": "Observed incident",
                    "endpointId": 1,
                    "incidentId": 1,
                    "alertId": None,
                    "eventId": None,
                    "pid": None,
                    "processName": None,
                    "destination": None,
                    "protocol": None,
                    "occurredAt": occurred_at,
                    "severity": "HIGH",
                    "eventType": None,
                    "riskScore": None,
                }
            ],
            "edges": [],
            "nodeCount": 1,
            "edgeCount": 0,
            "truncated": False,
            "partial": False,
            "warnings": [],
            "fallback": {
                "timelineAvailable": True,
                "alertTableAvailable": True,
                "eventTableAvailable": False,
            },
        }
    )
    dumped = model.model_dump(mode="json", by_alias=True)
    assert dumped["nodes"][0]["eventId"] is None
    assert dumped["edges"] == []
    assert dumped["warnings"] == []
    assert InvestigationEvidence.OBSERVED.value == "OBSERVED"
