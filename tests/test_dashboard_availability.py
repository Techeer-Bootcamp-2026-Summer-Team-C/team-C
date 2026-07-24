from datetime import UTC, datetime
from types import SimpleNamespace

from backend.summary_service import SummaryService


def test_dashboard_availability_merges_contiguous_queryable_ranges_and_preserves_gaps() -> None:
    rows = [
        _range("2026-07-10T00:00:00Z", "2026-07-11T00:00:00Z"),
        _range("2026-07-11T00:00:00Z", "2026-07-12T00:00:00Z"),
        _range("2026-07-14T00:00:00Z", "2026-07-15T00:00:00Z"),
        _range("2026-07-14T12:00:00Z", "2026-07-16T00:00:00Z"),
    ]
    requested_endpoint_ids: list[list[int] | None] = []
    metadata = SimpleNamespace(
        queryable_ranges=lambda *, endpoint_ids: (
            requested_endpoint_ids.append(endpoint_ids) or rows
        )
    )
    service = SummaryService(
        endpoints=SimpleNamespace(),
        alerts=SimpleNamespace(),
        incidents=SimpleNamespace(),
        metadata=metadata,
        events=SimpleNamespace(),
        failures=SimpleNamespace(),
        event_service=SimpleNamespace(),
    )

    result = service.availability(endpoint_ids=[7, 9])

    assert requested_endpoint_ids == [[7, 9]]
    assert result.model_dump(mode="json", by_alias=True) == {
        "availableRanges": [
            {"from": "2026-07-10T00:00:00Z", "to": "2026-07-12T00:00:00Z"},
            {"from": "2026-07-14T00:00:00Z", "to": "2026-07-16T00:00:00Z"},
        ]
    }


def _range(from_: str, to: str) -> dict[str, datetime]:
    return {
        "bucket_start_at": datetime.fromisoformat(from_.replace("Z", "+00:00")).astimezone(UTC),
        "bucket_end_at": datetime.fromisoformat(to.replace("Z", "+00:00")).astimezone(UTC),
    }
