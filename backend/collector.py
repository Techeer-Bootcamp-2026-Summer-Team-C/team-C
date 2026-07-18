import json
import zlib
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, TypeAdapter, ValidationError

from .contracts.collector import (
    AgentHeartbeatData,
    AgentHeartbeatRequest,
    AgentRegisterData,
    AgentRegisterRequest,
    L7Event,
    RejectedEventDto,
    TelemetryBatchData,
    TelemetryEvent,
)
from .contracts.common import ContractModel, UtcDateTime
from .contracts.enums import EndpointStatus
from .errors import PayloadTooLargeError, RequestValidationError, ServiceUnavailableError
from .kafka import RAW_TOPIC, ProducerPort
from .storage.models import AgentCertificateIdentity, EndpointAuthContext
from .storage.postgres import EndpointRepository
from .workers import canonical_json

MAX_BODY_BYTES = 5 * 1024 * 1024
EVENT_ADAPTER = TypeAdapter(TelemetryEvent)


class ConnectionContext(Protocol):
    def __enter__(self) -> Any: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...


class CollectorRuntimePort(Protocol):
    producer: ProducerPort

    def postgres(self) -> ConnectionContext: ...


class TelemetryEnvelope(ContractModel):
    schema_version: Literal[1]
    batch_id: UUID
    agent_id: str
    sent_at: UtcDateTime
    events: Annotated[list[dict[str, Any]], Field(min_length=1)]


class CollectorService:
    def __init__(
        self,
        runtime: CollectorRuntimePort,
        *,
        raw_topic: str | None = None,
        now=lambda: datetime.now(UTC),
    ) -> None:
        self.runtime = runtime
        self.raw_topic = raw_topic or getattr(runtime, "raw_topic", RAW_TOPIC)
        self.now = now

    def register(
        self,
        request: AgentRegisterRequest,
        certificate: AgentCertificateIdentity,
        *,
        request_id: str,
    ) -> tuple[AgentRegisterData, bool]:
        received_at = self.now()
        self._validate_certificate_window(certificate, received_at)
        with self.runtime.postgres() as connection:
            result = EndpointRepository(connection).register_agent(
                request,
                certificate,
                received_at=received_at,
                request_id=request_id,
            )
        return (
            AgentRegisterData(
                endpoint_id=result.endpoint_id,
                agent_id=result.agent_id,
                status=EndpointStatus(result.status),
                heartbeat_interval_seconds=30,
                registered_at=result.registered_at,
            ),
            result.created,
        )

    def heartbeat(
        self,
        request: AgentHeartbeatRequest,
        certificate: AgentCertificateIdentity,
    ) -> AgentHeartbeatData:
        received_at = self.now()
        with self.runtime.postgres() as connection:
            repository = EndpointRepository(connection)
            endpoint = repository.authenticate_agent(request.agent_id, certificate, now=received_at)
            repository.heartbeat(endpoint.endpoint_id, request, received_at=received_at)
        return AgentHeartbeatData(
            server_time=received_at,
            next_heartbeat_seconds=30,
            endpoint_status=EndpointStatus.ONLINE,
        )

    def telemetry(
        self,
        body: bytes,
        *,
        content_encoding: str | None,
        certificate: AgentCertificateIdentity,
    ) -> TelemetryBatchData:
        decoded = self._decode_body(body, content_encoding)
        try:
            raw = json.loads(decoded)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise RequestValidationError("Request body must be valid JSON.") from error
        if not isinstance(raw, dict):
            raise RequestValidationError("Request body must be a JSON object.")
        events = raw.get("events")
        if isinstance(events, list) and len(events) > 100:
            raise PayloadTooLargeError("A telemetry batch cannot contain more than 100 events.")
        try:
            envelope = TelemetryEnvelope.model_validate(raw)
        except ValidationError as error:
            raise RequestValidationError("Telemetry batch envelope is invalid.") from error

        received_at = self.now()
        with self.runtime.postgres() as connection:
            endpoint = EndpointRepository(connection).authenticate_agent(
                envelope.agent_id,
                certificate,
                now=received_at,
            )
        accepted: list[str] = []
        rejected: list[RejectedEventDto] = []
        seen: set[str] = set()
        publish_candidates = 0
        for raw_event in envelope.events:
            event_id = str(raw_event.get("eventId", ""))
            if event_id in seen:
                rejected.append(self._rejection(event_id, "DUPLICATE_EVENT_ID", "eventId is duplicated in the batch."))
                continue
            seen.add(event_id)
            try:
                UUID(event_id)
                event = EVENT_ADAPTER.validate_python(raw_event)
            except (ValueError, ValidationError):
                rejected.append(self._rejection(event_id, "INVALID_EVENT", "Telemetry event is invalid."))
                continue
            if event.occurred_at > received_at + timedelta(minutes=5):
                rejected.append(
                    self._rejection(event_id, "EVENT_TIME_IN_FUTURE", "occurredAt exceeds the allowed future window.")
                )
                continue
            event = self._sanitize_event(event)
            publish_candidates += 1
            message = self._raw_message(envelope, endpoint, event)
            if self.runtime.producer.publish(
                self.raw_topic,
                key=str(endpoint.endpoint_id),
                value=canonical_json(message),
            ):
                accepted.append(event_id)
            else:
                rejected.append(
                    RejectedEventDto(
                        event_id=event_id,
                        code="KAFKA_PUBLISH_FAILED",
                        message="Kafka broker did not acknowledge the event.",
                        retryable=True,
                    )
                )
        if publish_candidates > 0 and not accepted:
            raise ServiceUnavailableError("Kafka broker did not acknowledge any telemetry event.")
        return TelemetryBatchData(
            batch_id=str(envelope.batch_id),
            accepted_event_ids=accepted,
            rejected_events=rejected,
        )

    def _decode_body(self, body: bytes, content_encoding: str | None) -> bytes:
        if len(body) > MAX_BODY_BYTES:
            raise PayloadTooLargeError("Telemetry body exceeds 5 MiB.")
        if content_encoding not in {None, "", "identity", "gzip"}:
            raise RequestValidationError("Unsupported Content-Encoding.")
        if content_encoding == "gzip":
            try:
                decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                body = decompressor.decompress(body, MAX_BODY_BYTES + 1)
                if len(body) <= MAX_BODY_BYTES:
                    body += decompressor.flush(MAX_BODY_BYTES + 1 - len(body))
            except zlib.error as error:
                raise RequestValidationError("Telemetry gzip body is invalid.") from error
            if len(body) > MAX_BODY_BYTES:
                raise PayloadTooLargeError("Uncompressed telemetry body exceeds 5 MiB.")
            if not decompressor.eof or decompressor.unused_data:
                raise RequestValidationError("Telemetry gzip body is invalid.")
        if len(body) > MAX_BODY_BYTES:
            raise PayloadTooLargeError("Uncompressed telemetry body exceeds 5 MiB.")
        return body

    def _validate_certificate_window(self, certificate: AgentCertificateIdentity, now: datetime) -> None:
        if certificate.issued_at > now or certificate.expires_at <= now:
            from .errors import InvalidAgentCertificateError

            raise InvalidAgentCertificateError()

    def _sanitize_event(self, event: TelemetryEvent) -> TelemetryEvent:
        if isinstance(event, L7Event) and event.payload.url is not None:
            parts = urlsplit(event.payload.url)
            event.payload.url = parts.path or "/"
        return event

    def _raw_message(
        self,
        envelope: TelemetryEnvelope,
        endpoint: EndpointAuthContext,
        event: TelemetryEvent,
    ) -> dict[str, Any]:
        return {
            "agentId": endpoint.agent_id,
            "batchId": str(envelope.batch_id),
            "endpointId": endpoint.endpoint_id,
            "event": event.model_dump(mode="json", by_alias=True, exclude_unset=True),
            "hostname": endpoint.hostname,
            "ipAddress": endpoint.ip_address,
            "osType": endpoint.os_type.value,
            "schemaVersion": envelope.schema_version,
        }

    @staticmethod
    def _rejection(event_id: str, code: str, message: str) -> RejectedEventDto:
        return RejectedEventDto(event_id=event_id, code=code, message=message, retryable=False)
