from typing import Literal

from pydantic import Field, model_validator

from .common import ContractModel, EndpointIdList, NonNegativeInt, PositiveId, UtcDateTime, validate_max_31_day_range
from .enums import StorageBackend, StorageClass, StorageStatus


class ArchiveRestoreRequest(ContractModel):
    endpoint_ids: EndpointIdList = Field(description="복원할 엔드포인트 ID입니다.")
    from_: UtcDateTime = Field(alias="from", description="복원 범위의 시작 시각입니다.")
    to: UtcDateTime = Field(description="복원 범위의 종료 시각입니다. 최대 복원 범위는 31일입니다.")

    @model_validator(mode="after")
    def validate_range(self) -> "ArchiveRestoreRequest":
        validate_max_31_day_range(self.from_, self.to)
        return self


class ArchiveBucketDto(ContractModel):
    endpoint_id: PositiveId
    bucket_start_at: UtcDateTime
    bucket_end_at: UtcDateTime
    storage_backend: StorageBackend
    storage_class: StorageClass
    storage_status: StorageStatus
    storage_path: str
    event_count: NonNegativeInt
    size_bytes: NonNegativeInt | None
    checksum_sha256: str | None
    archived_at: UtcDateTime | None
    archive_verified_at: UtcDateTime | None
    restore_requested_at: UtcDateTime | None
    restored_at: UtcDateTime | None
    restore_expires_at: UtcDateTime | None
    last_error: str | None


class ArchiveRestoreStartDto(ContractModel):
    endpoint_ids: list[PositiveId]
    from_: UtcDateTime = Field(alias="from")
    to: UtcDateTime
    restore_days: Literal[7]
    retrieval_tier: Literal["Standard"]
    buckets: list[ArchiveBucketDto]
