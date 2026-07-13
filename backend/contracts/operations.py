from .common import ContractModel, NonNegativeInt, UtcDateTime
from .enums import SensorHealth, WorkerStatus


class ServiceHealthDto(ContractModel):
    service: str
    status: SensorHealth
    latency_ms: NonNegativeInt
    detail: str


class PipelineWorkerDto(ContractModel):
    worker: str
    group_id: str
    topic: str
    status: WorkerStatus
    member_count: NonNegativeInt | None
    lag: NonNegativeInt | None
    detail: str


class OperationsHealthDto(ContractModel):
    checked_at: UtcDateTime
    status: SensorHealth
    services: list[ServiceHealthDto]
    workers: list[PipelineWorkerDto]
