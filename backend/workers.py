import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from .detection import DetectionEngine
from .errors import ArchivedDayImmutableError
from .failure import FailureSink
from .kafka import VALIDATED_TOPIC, ConsumedMessage, ConsumerPort, ProducerPort
from .storage.clickhouse import EventRepository
from .storage.models import IncidentInsert
from .storage.postgres import AlertRepository, EndpointRepository, IncidentRepository, IngestMetadataRepository

RETRY_DELAYS_SECONDS = (1, 5, 30)
LOGGER = logging.getLogger(__name__)


class EventIdentityConflictError(Exception):
    pass


class PermanentMessageError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RetryFailure:
    error: Exception
    retry_count: int


def run_with_retries(
    operation: Callable[[], None],
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> RetryFailure | None:
    try:
        operation()
        return None
    except (ArchivedDayImmutableError, EventIdentityConflictError, PermanentMessageError):
        raise
    except Exception as error:
        last_error = error
    for delay in RETRY_DELAYS_SECONDS:
        sleep(delay)
        try:
            operation()
            return None
        except (ArchivedDayImmutableError, EventIdentityConflictError, PermanentMessageError):
            raise
        except Exception as error:
            last_error = error
    return RetryFailure(last_error, len(RETRY_DELAYS_SECONDS))


class EventStorageWorker:
    consumer_name = "event-storage-worker"

    def __init__(
        self,
        *,
        consumer: ConsumerPort,
        producer: ProducerPort,
        events: EventRepository,
        metadata: IngestMetadataRepository,
        failure_sink: FailureSink,
        validated_topic: str = VALIDATED_TOPIC,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.consumer = consumer
        self.producer = producer
        self.events = events
        self.metadata = metadata
        self.failure_sink = failure_sink
        self.validated_topic = validated_topic
        self.sleep = sleep
        self.now = now
        self.reset_requested = False

    def run_once(self, timeout: float = 1.0) -> bool:
        self.reset_requested = False
        message = self.consumer.consume_one(timeout)
        if message is None:
            return False
        failure_code: str | None = None
        retryable = True
        retry_count = 0
        try:
            retry_failure = run_with_retries(lambda: self._process(message), sleep=self.sleep)
            if retry_failure is None:
                self.consumer.commit(message)
                return True
            error = retry_failure.error
            retry_count = retry_failure.retry_count
            self.reset_requested = True
        except ArchivedDayImmutableError as caught:
            error = caught
            failure_code = "ARCHIVED_DAY_IMMUTABLE"
            retryable = False
        except EventIdentityConflictError as caught:
            error = caught
            failure_code = "EVENT_IDENTITY_CONFLICT"
            retryable = False
        except PermanentMessageError as caught:
            error = caught
            failure_code = "INVALID_MESSAGE"
            retryable = False

        LOGGER.warning(
            "worker message failed topic=%s partition=%s offset=%s consumer=%s code=%s retryable=%s retries=%s",
            message.topic,
            message.partition,
            message.offset,
            self.consumer_name,
            failure_code or "PROCESSING_ERROR",
            retryable,
            retry_count,
        )

        try:
            self.failure_sink.record(
                message,
                consumer_name=self.consumer_name,
                failure_stage="EVENT_STORAGE",
                failure_code=failure_code,
                error_message=str(error),
                retryable=retryable,
                retry_count=retry_count,
                failed_at=self.now(),
            )
        except Exception:
            self.reset_requested = True
            LOGGER.exception(
                "failure persistence failed; rewinding topic=%s partition=%s offset=%s consumer=%s",
                message.topic,
                message.partition,
                message.offset,
                self.consumer_name,
            )
            self.consumer.rewind(message)
            return False
        self.consumer.commit(message)
        return True

    def _process(self, message: ConsumedMessage) -> None:
        try:
            raw = json.loads(message.value)
            if not isinstance(raw, dict):
                raise TypeError("message root must be an object")
            record = normalize_event(raw, ingested_at=self.now())
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise PermanentMessageError("Kafka message payload is invalid") from error
        event_id = record["event_id"]
        existing = self.events.identity(event_id)
        if existing is not None:
            if (
                existing.endpoint_id != record["endpoint_id"]
                or existing.agent_id != record["agent_id"]
                or existing.payload_sha256 != record["payload_sha256"]
            ):
                raise EventIdentityConflictError("eventId exists with a different identity or payload")
        else:
            with self.metadata.hot_ingest_guard(
                endpoint_id=record["endpoint_id"],
                occurred_at=record["occurred_at"],
                now=self.now(),
            ):
                self.events.insert([record])
        validated = {
            "event": json_ready(record),
            "raw": raw,
        }
        if not self.producer.publish(
            self.validated_topic,
            key=str(record["endpoint_id"]),
            value=canonical_json(validated),
        ):
            raise RuntimeError("telemetry.validated broker acknowledgement failed")


class DetectionWorker:
    consumer_name = "detection-worker"

    def __init__(
        self,
        *,
        consumer: ConsumerPort,
        engine: DetectionEngine,
        alerts: AlertRepository,
        incidents: IncidentRepository,
        failure_sink: FailureSink,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.consumer = consumer
        self.engine = engine
        self.alerts = alerts
        self.incidents = incidents
        self.failure_sink = failure_sink
        self.sleep = sleep
        self.now = now
        self.reset_requested = False

    def run_once(self, timeout: float = 1.0) -> bool:
        self.reset_requested = False
        message = self.consumer.consume_one(timeout)
        if message is None:
            return False
        failure_code: str | None = None
        retryable = True
        retry_count = 0
        try:
            retry_failure = run_with_retries(lambda: self._process(message), sleep=self.sleep)
            if retry_failure is None:
                self.consumer.commit(message)
                return True
            error = retry_failure.error
            retry_count = retry_failure.retry_count
            self.reset_requested = True
        except PermanentMessageError as caught:
            error = caught
            failure_code = "INVALID_MESSAGE"
            retryable = False

        LOGGER.warning(
            "worker message failed topic=%s partition=%s offset=%s consumer=%s code=%s retryable=%s retries=%s",
            message.topic,
            message.partition,
            message.offset,
            self.consumer_name,
            failure_code or "PROCESSING_ERROR",
            retryable,
            retry_count,
        )
        try:
            self.failure_sink.record(
                message,
                consumer_name=self.consumer_name,
                failure_stage="DETECTION",
                failure_code=failure_code,
                error_message=str(error),
                retryable=retryable,
                retry_count=retry_count,
                failed_at=self.now(),
            )
        except Exception:
            self.reset_requested = True
            LOGGER.exception(
                "failure persistence failed; rewinding topic=%s partition=%s offset=%s consumer=%s",
                message.topic,
                message.partition,
                message.offset,
                self.consumer_name,
            )
            self.consumer.rewind(message)
            return False
        self.consumer.commit(message)
        return True

    def _process(self, message: ConsumedMessage) -> None:
        try:
            validated = json.loads(message.value)
            if not isinstance(validated, dict):
                raise TypeError("message root must be an object")
            event = dict(validated["event"])
            event["occurred_at"] = parse_timestamp(event["occurred_at"])
            event["event_id"] = UUID(event["event_id"])
            event["endpoint_id"] = int(event["endpoint_id"])
            event["agent_id"] = str(event["agent_id"])
            event["event_type"] = str(event["event_type"])
            if event.get("batch_id") is not None:
                event["batch_id"] = UUID(event["batch_id"])
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise PermanentMessageError("Kafka message payload is invalid") from error
        detected_at = self.now()
        for match in self.engine.evaluate(event, detected_at=detected_at):
            stored_alert = self.alerts.insert_if_absent(match.alert)
            if match.incident is None:
                continue
            stored_incident = self.incidents.upsert(
                IncidentInsert(
                    endpoint_id=match.incident.endpoint_id,
                    correlation_key=match.incident.correlation_key,
                    window_start_at=match.incident.window_start_at,
                    window_end_at=match.incident.window_end_at,
                    title=match.alert.title,
                    description=match.alert.summary,
                    severity=match.alert.severity,
                    detected_at=detected_at,
                )
            )
            self.incidents.link_alert(
                incident_id=stored_incident.incident_id,
                alert_id=stored_alert.alert_id,
                linked_at=detected_at,
            )


class LifecycleTasks:
    def __init__(self, endpoints: EndpointRepository, incidents: IncidentRepository) -> None:
        self.endpoints = endpoints
        self.incidents = incidents

    def run_once(self, *, now: datetime) -> tuple[int, int]:
        offline = self.mark_offline(now=now)
        closed = self.close_incidents(now=now)
        return offline, closed

    def mark_offline(self, *, now: datetime) -> int:
        return self.endpoints.mark_offline(cutoff=now - timedelta(minutes=2), updated_at=now)

    def close_incidents(self, *, now: datetime) -> int:
        return self.incidents.close_expired(now)


def normalize_event(raw: dict[str, Any], *, ingested_at: datetime) -> dict[str, Any]:
    event = raw["event"]
    payload = event["payload"]
    identity_payload = {
        "eventType": event["eventType"],
        "occurredAt": event["occurredAt"],
        "payload": payload,
    }
    raw_payload = canonical_json(identity_payload).decode()
    answers = payload.get("answers")
    return {
        "event_id": UUID(event["eventId"]),
        "batch_id": UUID(raw["batchId"]),
        "endpoint_id": int(raw["endpointId"]),
        "agent_id": str(raw["agentId"]),
        "hostname": str(raw["hostname"]),
        "os_type": str(raw["osType"]),
        "ip_address": raw.get("ipAddress"),
        "event_type": str(event["eventType"]),
        "occurred_at": parse_timestamp(event["occurredAt"]),
        "ingested_at": ingested_at,
        "process_name": payload.get("processName"),
        "process_path": payload.get("processPath"),
        "pid": payload.get("pid"),
        "ppid": payload.get("ppid"),
        "command_line": payload.get("commandLine"),
        "user_name": payload.get("userName"),
        "file_path": payload.get("filePath"),
        "file_action": payload.get("action"),
        "file_hash_sha256": payload.get("sha256"),
        "remote_ip": payload.get("remoteIp"),
        "remote_domain": payload.get("remoteDomain"),
        "remote_port": payload.get("remotePort"),
        "protocol": payload.get("protocol"),
        "dns_query": payload.get("query"),
        "dns_record_type": payload.get("recordType"),
        "dns_response_code": payload.get("responseCode"),
        "dns_answers_json": canonical_json(answers).decode() if answers is not None else None,
        "l7_protocol": payload.get("l7Protocol"),
        "http_method": payload.get("httpMethod"),
        "http_host": payload.get("httpHost"),
        "url": payload.get("url"),
        "http_status_code": payload.get("httpStatusCode"),
        "http_user_agent": payload.get("httpUserAgent"),
        "tls_sni": payload.get("tlsSni"),
        "tls_version": payload.get("tlsVersion"),
        "tls_certificate_subject": payload.get("tlsCertificateSubject"),
        "tls_certificate_issuer": payload.get("tlsCertificateIssuer"),
        "tls_certificate_sha256": payload.get("tlsCertificateSha256"),
        "raw_payload": raw_payload,
        "payload_sha256": hashlib.sha256(raw_payload.encode()).hexdigest(),
        "schema_version": int(raw["schemaVersion"]),
        "created_at": ingested_at,
        "updated_at": ingested_at,
        "is_delete": 0,
    }


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def json_ready(value: dict[str, Any]) -> dict[str, Any]:
    ready: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, datetime):
            ready[key] = item.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        elif isinstance(item, (UUID, Decimal)):
            ready[key] = str(item)
        else:
            ready[key] = item
    return ready


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
