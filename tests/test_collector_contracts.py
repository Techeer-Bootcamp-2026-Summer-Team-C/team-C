import pytest
from pydantic import ValidationError

from backend.contracts.collector import TelemetryBatchRequest


def test_telemetry_discriminated_payload_and_aliases() -> None:
    request = TelemetryBatchRequest.model_validate(
        {
            "schemaVersion": 1,
            "batchId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e000",
            "agentId": "agent-win-001",
            "sentAt": "2026-07-11T00:00:05Z",
            "events": [
                {
                    "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e001",
                    "eventType": "DNS_QUERY",
                    "occurredAt": "2026-07-11T00:00:04.123Z",
                    "payload": {"query": "example.com", "recordType": "A", "answers": []},
                }
            ],
        }
    )
    dumped = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert dumped["schemaVersion"] == 1
    assert dumped["events"][0]["eventType"] == "DNS_QUERY"
    assert dumped["events"][0]["payload"]["answers"] == []


def test_optional_request_field_rejects_explicit_null() -> None:
    with pytest.raises(ValidationError):
        TelemetryBatchRequest.model_validate(
            {
                "schemaVersion": 1,
                "batchId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e000",
                "agentId": "agent-win-001",
                "sentAt": "2026-07-11T00:00:05Z",
                "events": [
                    {
                        "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e001",
                        "eventType": "DNS_QUERY",
                        "occurredAt": "2026-07-11T00:00:04.123Z",
                        "payload": {"query": "example.com", "recordType": "A", "responseCode": None},
                    }
                ],
            }
        )
