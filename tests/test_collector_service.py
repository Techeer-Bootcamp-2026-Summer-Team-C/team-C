import gzip
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import backend.collector as collector_module
from backend.collector import CollectorService
from backend.contracts.collector import AgentHeartbeatData, AgentRegisterData
from backend.contracts.enums import EndpointStatus, OsType
from backend.errors import AgentIdentityConflictError, PayloadTooLargeError, ServiceUnavailableError
from backend.main import create_app, get_collector_service
from backend.storage.models import AgentCertificateIdentity, EndpointAuthContext

NOW = datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
EVENT_ID = "018ff8f4-86de-7b25-9b8a-2d22f6a3e001"
BATCH_ID = "018ff8f4-86de-7b25-9b8a-2d22f6a3e000"


def identity() -> AgentCertificateIdentity:
    return AgentCertificateIdentity(
        "CN=agent",
        "agent-win-001",
        "a" * 64,
        NOW - timedelta(days=1),
        NOW + timedelta(days=1),
    )


def headers(fingerprint: str = "a" * 64) -> dict[str, str]:
    return {
        "X-EDR-mTLS-Verify": "SUCCESS",
        "X-EDR-Certificate-Subject": "CN=agent",
        "X-EDR-Certificate-SAN-Agent-ID": "agent-win-001",
        "X-EDR-Certificate-Fingerprint-SHA256": fingerprint,
        "X-EDR-Certificate-Not-Before": "Jul 11 01:00:00 2026 GMT",
        "X-EDR-Certificate-Not-After": "Jul 13 01:00:00 2026 GMT",
    }


def batch(events: list[dict] | None = None) -> dict:
    return {
        "schemaVersion": 1,
        "batchId": BATCH_ID,
        "agentId": "agent-win-001",
        "sentAt": "2026-07-12T01:00:00Z",
        "events": events
        or [
            {
                "eventId": EVENT_ID,
                "eventType": "DNS_QUERY",
                "occurredAt": "2026-07-12T00:59:59Z",
                "payload": {"query": "example.com", "recordType": "A", "answers": []},
            }
        ],
    }


class FakeProducer:
    def __init__(self, acknowledgements: list[bool] | None = None) -> None:
        self.acknowledgements = acknowledgements or [True]
        self.messages: list[tuple[str, str, bytes]] = []

    def publish(self, topic: str, *, key: str, value: bytes, headers=None) -> bool:
        self.messages.append((topic, key, value))
        return self.acknowledgements.pop(0) if self.acknowledgements else True

    def check(self) -> None:
        return None


class FakeRuntime:
    def __init__(self, producer: FakeProducer) -> None:
        self.producer = producer

    @contextmanager
    def postgres(self):
        yield object()

    def check_ready(self) -> None:
        return None


class FakeEndpointRepository:
    def __init__(self, _connection) -> None:
        pass

    def authenticate_agent(self, agent_id, certificate, *, now) -> EndpointAuthContext:
        assert certificate.fingerprint_sha256 == "a" * 64
        return EndpointAuthContext(1001, agent_id, "WIN-ENDPOINT-01", OsType.WINDOWS, "10.0.0.1")


def service(monkeypatch, acknowledgements: list[bool] | None = None) -> tuple[CollectorService, FakeProducer]:
    producer = FakeProducer(acknowledgements)
    monkeypatch.setattr(collector_module, "EndpointRepository", FakeEndpointRepository)
    return CollectorService(FakeRuntime(producer), now=lambda: NOW), producer


def test_telemetry_normal_partial_duplicate_and_gzip(monkeypatch) -> None:
    collector, producer = service(monkeypatch, [True, True])
    future = dict(batch()["events"][0])
    future["eventId"] = "018ff8f4-86de-7b25-9b8a-2d22f6a3e002"
    future["occurredAt"] = "2026-07-12T01:05:00.001Z"
    duplicate = dict(batch()["events"][0])
    body = json.dumps(batch([batch()["events"][0], future, duplicate])).encode()
    result = collector.telemetry(gzip.compress(body), content_encoding="gzip", certificate=identity())
    assert result.accepted_event_ids == [EVENT_ID]
    assert [item.code for item in result.rejected_events] == ["EVENT_TIME_IN_FUTURE", "DUPLICATE_EVENT_ID"]
    assert len(producer.messages) == 1
    assert producer.messages[0][1] == "1001"


def test_event_validation_is_partial_and_pcap_is_never_published(monkeypatch) -> None:
    collector, producer = service(monkeypatch)
    invalid = batch()["events"][0]
    invalid["payload"]["pcapBytes"] = "forbidden"
    result = collector.telemetry(json.dumps(batch([invalid])).encode(), content_encoding=None, certificate=identity())
    assert result.accepted_event_ids == []
    assert result.rejected_events[0].code == "INVALID_EVENT"
    assert producer.messages == []


def test_envelope_and_size_limits(monkeypatch) -> None:
    collector, _producer = service(monkeypatch)
    with pytest.raises(PayloadTooLargeError):
        collector.telemetry(b"x" * (5 * 1024 * 1024 + 1), content_encoding=None, certificate=identity())
    oversized = batch([batch()["events"][0] for _ in range(101)])
    with pytest.raises(PayloadTooLargeError):
        collector.telemetry(json.dumps(oversized).encode(), content_encoding=None, certificate=identity())
    with pytest.raises(Exception, match="envelope"):
        collector.telemetry(b"{}", content_encoding=None, certificate=identity())


def test_all_kafka_acknowledgements_failed_is_503(monkeypatch) -> None:
    collector, _producer = service(monkeypatch, [False])
    with pytest.raises(ServiceUnavailableError) as caught:
        collector.telemetry(json.dumps(batch()).encode(), content_encoding=None, certificate=identity())
    assert caught.value.status_code == 503


class FakeCollector:
    def __init__(self) -> None:
        self.created = True

    def register(self, request, certificate, *, request_id):
        if request.hostname == "conflict":
            raise AgentIdentityConflictError()
        data = AgentRegisterData(
            endpoint_id=1001,
            agent_id=request.agent_id,
            status=EndpointStatus.ONLINE,
            heartbeat_interval_seconds=30,
            registered_at=NOW,
        )
        created, self.created = self.created, False
        return data, created

    def heartbeat(self, request, certificate):
        return AgentHeartbeatData(server_time=NOW, next_heartbeat_seconds=30, endpoint_status=EndpointStatus.ONLINE)


def registration_body(hostname: str = "WIN-ENDPOINT-01") -> dict:
    return {
        "agentId": "agent-win-001",
        "hostname": hostname,
        "osType": "WINDOWS",
        "osVersion": "11",
        "agentVersion": "0.1.0",
        "agentBuildId": "win-x64-1",
        "agentArch": "X64",
        "capabilityCodes": ["PROCESS_EXECUTION"],
    }


def test_http_registration_status_and_error_envelope() -> None:
    app = create_app(FakeRuntime(FakeProducer()))
    fake = FakeCollector()
    app.dependency_overrides[get_collector_service] = lambda: fake
    client = TestClient(app)
    first = client.post("/api/v1/collector/agents/register", headers=headers(), json=registration_body())
    second = client.post("/api/v1/collector/agents/register", headers=headers(), json=registration_body())
    conflict = client.post("/api/v1/collector/agents/register", headers=headers(), json=registration_body("conflict"))
    assert first.status_code == 201
    assert second.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDENTITY_CONFLICT"
    assert first.json()["data"]["registeredAt"].endswith("Z")


def test_http_rejects_untrusted_certificate_headers() -> None:
    app = create_app(FakeRuntime(FakeProducer()))
    app.dependency_overrides[get_collector_service] = lambda: FakeCollector()
    response = TestClient(app).post("/api/v1/collector/agents/register", json=registration_body())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_AGENT_CERTIFICATE"


def test_http_returns_503_when_no_kafka_event_is_acknowledged() -> None:
    class KafkaUnavailableCollector(FakeCollector):
        def telemetry(self, body, *, content_encoding, certificate):
            raise ServiceUnavailableError("Kafka broker did not acknowledge any telemetry event.")

    app = create_app(FakeRuntime(FakeProducer()))
    app.dependency_overrides[get_collector_service] = lambda: KafkaUnavailableCollector()
    response = TestClient(app).post(
        "/api/v1/collector/telemetry/batches",
        headers=headers(),
        json=batch(),
    )
    assert response.status_code == 503
    assert response.json()["error"]["retryable"] is True
