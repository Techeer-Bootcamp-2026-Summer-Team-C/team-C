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


def test_agent_event_aliases_and_optional_fields_match_the_collector_contract() -> None:
    request = TelemetryBatchRequest.model_validate(
        {
            "schemaVersion": 1,
            "batchId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e010",
            "agentId": "agent-win-001",
            "sentAt": "2026-07-11T00:00:05Z",
            "events": [
                {
                    "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e011",
                    "eventType": "PROCESS_EXECUTION",
                    "occurredAt": "2026-07-11T00:00:04Z",
                    "payload": {
                        "processName": "pwsh.exe",
                        "pid": 42,
                        "commandLine": "pwsh.exe -EncodedCommand <redacted>",
                    },
                },
                {
                    "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e012",
                    "eventType": "NETWORK_CONNECTION",
                    "occurredAt": "2026-07-11T00:00:04Z",
                    "payload": {"protocol": "TCP", "remoteIp": "203.0.113.10", "remotePort": 443, "pid": 42},
                },
                {
                    "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e013",
                    "eventType": "FILE_EVENT",
                    "occurredAt": "2026-07-11T00:00:04Z",
                    "payload": {"filePath": "C:\\Temp\\artifact.bin", "action": "CREATED"},
                },
                {
                    "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e014",
                    "eventType": "L7_EVENT",
                    "occurredAt": "2026-07-11T00:00:04Z",
                    "payload": {
                        "l7Protocol": "TLS",
                        "tlsSni": "example.com",
                        "tlsVersion": "TLS1.2",
                        "tlsCertificateSubject": "CN=example.com",
                        "tlsCertificateIssuer": "CN=Example CA",
                        "tlsCertificateSha256": "a" * 64,
                    },
                },
            ],
        }
    )

    dumped = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert "remoteDomain" not in dumped["events"][1]["payload"]
    assert dumped["events"][2]["payload"]["action"] == "CREATE"
    assert dumped["events"][3]["payload"]["tlsCertificateSubject"] == "CN=example.com"
    assert "tlsSubject" not in dumped["events"][3]["payload"]


@pytest.mark.parametrize("action", ["CREATE", "DELETE", "MODIFY", "RENAME"])
def test_file_action_canonical_values(action: str) -> None:
    request = TelemetryBatchRequest.model_validate(
        {
            "schemaVersion": 1,
            "batchId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e020",
            "agentId": "agent-mac-001",
            "sentAt": "2026-07-11T00:00:05Z",
            "events": [
                {
                    "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e021",
                    "eventType": "FILE_EVENT",
                    "occurredAt": "2026-07-11T00:00:04Z",
                    "payload": {"filePath": "/tmp/artifact.bin", "action": action},
                }
            ],
        }
    )
    assert request.events[0].payload.action == action


def test_file_action_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError):
        TelemetryBatchRequest.model_validate(
            {
                "schemaVersion": 1,
                "batchId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e030",
                "agentId": "agent-mac-001",
                "sentAt": "2026-07-11T00:00:05Z",
                "events": [
                    {
                        "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e031",
                        "eventType": "FILE_EVENT",
                        "occurredAt": "2026-07-11T00:00:04Z",
                        "payload": {"filePath": "/tmp/artifact.bin", "action": "UPSERT"},
                    }
                ],
            }
        )
