import base64
import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from .kafka import ConsumedMessage
from .storage.clickhouse import FailureRepository


class S3ClientPort(Protocol):
    def head_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class StoredFailure:
    failure_id: UUID
    object_key: str
    checksum_sha256: str
    size_bytes: int


def failure_id_for(message: ConsumedMessage, consumer_name: str, failure_stage: str) -> UUID:
    identity = json.dumps(
        [message.topic, message.partition, message.offset, consumer_name, failure_stage],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return uuid5(NAMESPACE_URL, "urn:edr:failure:v1:" + identity)


def deterministic_failure_payload(envelope: dict[str, Any]) -> bytes:
    canonical = json.dumps(envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return gzip.compress(canonical, compresslevel=9, mtime=0)


class FailureSink:
    def __init__(
        self,
        *,
        s3_client: S3ClientPort,
        bucket: str,
        repository: FailureRepository,
    ) -> None:
        self.s3 = s3_client
        self.bucket = bucket
        self.repository = repository

    def record(
        self,
        message: ConsumedMessage,
        *,
        consumer_name: str,
        failure_stage: str,
        failure_code: str | None,
        error_message: str,
        retryable: bool,
        retry_count: int,
        failed_at: datetime,
    ) -> StoredFailure:
        failure_id = failure_id_for(message, consumer_name, failure_stage)
        object_key = f"failures/{failure_id}/payload.json.gz"
        source_message = _failure_message(message.value)
        envelope = {
            "consumerName": consumer_name,
            "failureCode": failure_code,
            "failureStage": failure_stage,
            "message": source_message,
            "sourceOffset": message.offset,
            "sourcePartition": message.partition,
            "sourceTopic": message.topic,
        }
        payload = deterministic_failure_payload(envelope)
        checksum = hashlib.sha256(payload).hexdigest()
        self._put_idempotent(object_key, payload, checksum)

        source_mapping = source_message if isinstance(source_message, dict) else {}
        event_value = source_mapping.get("event", source_mapping)
        event = event_value if isinstance(event_value, dict) else {}
        event_id = _optional_uuid(event.get("eventId") or event.get("event_id"))
        endpoint_id = (
            source_mapping.get("endpointId")
            or source_mapping.get("endpoint_id")
            or event.get("endpointId")
            or event.get("endpoint_id")
        )
        row = {
            "failure_id": failure_id,
            "event_id": event_id,
            "endpoint_id": _optional_int(endpoint_id),
            "source_topic": message.topic,
            "source_partition": message.partition,
            "source_offset": message.offset,
            "consumer_name": consumer_name,
            "failure_stage": failure_stage,
            "failure_code": failure_code,
            "error_message": error_message,
            "retryable": int(retryable),
            "retry_count": retry_count,
            "payload_object_key": object_key,
            "payload_sha256": checksum,
            "payload_size_bytes": len(payload),
            "status": "FAILED",
            "failed_at": failed_at,
            "replay_count": 0,
            "last_replayed_at": None,
            "reprocess_outcome": None,
            "resolved_at": None,
            "retention_expires_at": failed_at + timedelta(days=90),
            "created_at": failed_at,
            "updated_at": failed_at,
        }
        self.repository.insert([row])
        if self.repository.latest_status(failure_id) != "FAILED":
            raise RuntimeError("ClickHouse failure record was not durably readable")
        return StoredFailure(failure_id, object_key, checksum, len(payload))

    def _put_idempotent(self, key: str, payload: bytes, checksum: str) -> None:
        try:
            current = self.s3.head_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            response = getattr(error, "response", {})
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status != 404 and response.get("Error", {}).get("Code") not in {"404", "NoSuchKey"}:
                raise
        else:
            metadata_checksum = current.get("Metadata", {}).get("sha256")
            if metadata_checksum == checksum and int(current.get("ContentLength", -1)) == len(payload):
                return
            existing = self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            if hashlib.sha256(existing).hexdigest() == checksum and len(existing) == len(payload):
                return
            raise RuntimeError("failure payload checksum collision")

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType="application/json",
            ContentEncoding="gzip",
            Metadata={"sha256": checksum},
        )
        durable = self.s3.head_object(Bucket=self.bucket, Key=key)
        if int(durable.get("ContentLength", -1)) != len(payload):
            raise RuntimeError("S3 failure payload length verification failed")

    def load_verified(self, failure: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        if not bool(failure["retryable"]):
            raise ValueError("failure is not retryable")
        retention_expires_at = failure["retention_expires_at"]
        if retention_expires_at.tzinfo is None:
            retention_expires_at = retention_expires_at.replace(tzinfo=UTC)
        if retention_expires_at <= now:
            raise ValueError("failure payload retention has expired")
        body = self.s3.get_object(Bucket=self.bucket, Key=str(failure["payload_object_key"]))["Body"].read()
        if len(body) != int(failure["payload_size_bytes"]):
            raise ValueError("failure payload size mismatch")
        if hashlib.sha256(body).hexdigest() != _fixed_string(failure["payload_sha256"]):
            raise ValueError("failure payload checksum mismatch")
        return json.loads(gzip.decompress(body))


def _fixed_string(value: Any) -> str:
    return value.decode("ascii") if isinstance(value, bytes) else str(value)


def _failure_message(value: bytes) -> Any:
    try:
        return json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"encoding": "base64", "raw": base64.b64encode(value).decode("ascii")}


def _optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
