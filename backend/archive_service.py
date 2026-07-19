import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol

from .contracts.archives import ArchiveBucketDto, ArchiveRestoreRequest, ArchiveRestoreStartDto
from .storage.postgres import IngestMetadataRepository


class RestoreObjectPort(Protocol):
    def restore(self, object_key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class RestoreObjectStatus:
    ongoing: bool
    expires_at: datetime | None = None


class RestoreStatusPort(RestoreObjectPort, Protocol):
    def status(self, object_key: str) -> RestoreObjectStatus | None: ...


class BotoRestoreObjectClient:
    def __init__(self, s3_client, *, bucket: str) -> None:
        self.s3 = s3_client
        self.bucket = bucket

    def restore(self, object_key: str) -> None:
        self.s3.restore_object(
            Bucket=self.bucket,
            Key=object_key,
            RestoreRequest={"Days": 7, "GlacierJobParameters": {"Tier": "Standard"}},
        )

    def status(self, object_key: str) -> RestoreObjectStatus | None:
        response = self.s3.head_object(Bucket=self.bucket, Key=object_key)
        restore = str(response.get("Restore") or "")
        if not restore:
            return None
        ongoing_match = re.search(r'ongoing-request="(true|false)"', restore)
        if ongoing_match is None:
            raise RuntimeError("S3 Restore header is malformed")
        ongoing = ongoing_match.group(1) == "true"
        if ongoing:
            return RestoreObjectStatus(ongoing=True)
        expiry_match = re.search(r'expiry-date="([^"]+)"', restore)
        if expiry_match is None:
            raise RuntimeError("Completed S3 Restore header has no expiry-date")
        expires_at = parsedate_to_datetime(expiry_match.group(1))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return RestoreObjectStatus(ongoing=False, expires_at=expires_at.astimezone(UTC))


class ArchiveService:
    def __init__(self, repository: IngestMetadataRepository, restore_client: RestoreObjectPort) -> None:
        self.repository = repository
        self.restore_client = restore_client

    def start_restore(
        self,
        request: ArchiveRestoreRequest,
        *,
        actor_identifier: str,
        request_id: str,
        now: datetime,
    ) -> tuple[ArchiveRestoreStartDto, int]:
        rows = self.repository.restore_buckets(request.endpoint_ids, request.from_, request.to)
        response_rows: list[dict] = []
        accepted = False
        for row in rows:
            status = str(row["storage_status"])
            if status in {"ARCHIVED", "RESTORE_FAILED", "EXPIRED"}:
                changed = self.repository.request_restore(
                    endpoint_id=int(row["endpoint_id"]),
                    bucket_start_at=row["bucket_start_at"],
                    actor_identifier=actor_identifier,
                    request_id=request_id,
                    requested_at=now,
                )
                if changed:
                    try:
                        self.restore_client.restore(str(row["storage_path"]))
                    except Exception as error:
                        self.repository.mark_restore_failed(
                            endpoint_id=int(row["endpoint_id"]),
                            bucket_start_at=row["bucket_start_at"],
                            error=f"{type(error).__name__}: {error}"[:1000],
                            failed_at=now,
                        )
                        raise
                    row["storage_status"] = "RESTORE_REQUESTED"
                    row["restore_requested_at"] = now
                    row["restored_at"] = None
                    row["restore_expires_at"] = None
                    row["last_error"] = None
                    accepted = True
                else:
                    current = self.repository.restore_bucket(
                        endpoint_id=int(row["endpoint_id"]),
                        bucket_start_at=row["bucket_start_at"],
                    )
                    if current is not None:
                        row = current
                        accepted = str(row["storage_status"]) == "RESTORE_REQUESTED"
            elif status == "RESTORE_REQUESTED":
                accepted = True
            response_rows.append(row)
        return (
            ArchiveRestoreStartDto(
                endpoint_ids=request.endpoint_ids,
                from_=request.from_,
                to=request.to,
                restore_days=7,
                retrieval_tier="Standard",
                buckets=[archive_bucket(row) for row in response_rows],
            ),
            202 if accepted else 200,
        )


def archive_bucket(row: dict) -> ArchiveBucketDto:
    return ArchiveBucketDto.model_validate({field: row.get(field) for field in ArchiveBucketDto.model_fields})
