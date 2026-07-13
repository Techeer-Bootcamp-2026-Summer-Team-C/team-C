from datetime import datetime
from typing import Protocol

from .contracts.archives import ArchiveBucketDto, ArchiveRestoreRequest, ArchiveRestoreStartDto
from .storage.postgres import IngestMetadataRepository


class RestoreObjectPort(Protocol):
    def restore(self, object_key: str) -> None: ...


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
                self.restore_client.restore(str(row["storage_path"]))
                changed = self.repository.request_restore(
                    endpoint_id=int(row["endpoint_id"]),
                    bucket_start_at=row["bucket_start_at"],
                    actor_identifier=actor_identifier,
                    request_id=request_id,
                    requested_at=now,
                )
                if changed:
                    row["storage_status"] = "RESTORE_REQUESTED"
                    row["restore_requested_at"] = now
                    row["restored_at"] = None
                    row["restore_expires_at"] = None
                    row["last_error"] = None
                    accepted = True
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
