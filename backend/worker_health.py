from pathlib import Path
from time import time

HEARTBEAT_DIRECTORY = Path("/tmp/edr-worker-health")
WORKER_NAMES = frozenset(
    {
        "event-storage-worker",
        "detection-worker",
        "storage-lifecycle-worker",
    }
)


def mark_worker_heartbeat(
    worker: str,
    *,
    checked_at: float | None = None,
    directory: Path = HEARTBEAT_DIRECTORY,
) -> None:
    path = _heartbeat_path(worker, directory)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(f"{checked_at if checked_at is not None else time():.6f}\n", encoding="utf-8")
    temporary_path.replace(path)


def worker_heartbeat_is_fresh(
    worker: str,
    *,
    max_age_seconds: float,
    checked_at: float | None = None,
    directory: Path = HEARTBEAT_DIRECTORY,
) -> bool:
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")
    path = _heartbeat_path(worker, directory)
    try:
        heartbeat_at = float(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, ValueError):
        return False
    age = (checked_at if checked_at is not None else time()) - heartbeat_at
    return 0 <= age <= max_age_seconds


def _heartbeat_path(worker: str, directory: Path) -> Path:
    if worker not in WORKER_NAMES:
        raise ValueError(f"unsupported worker: {worker}")
    return directory / worker
