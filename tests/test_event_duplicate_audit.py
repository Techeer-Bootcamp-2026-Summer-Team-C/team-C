from datetime import UTC, datetime

import pytest

from tools.audit_event_duplicates import audit_event_duplicates


class QueryResult:
    def __init__(self, rows) -> None:
        self.result_rows = rows


class FakeClient:
    def __init__(self, *, summary, findings=()) -> None:
        self.summary = summary
        self.findings = findings
        self.queries: list[tuple[str, dict | None]] = []

    def query(self, query, parameters=None):
        self.queries.append((query, parameters))
        return QueryResult([self.summary] if "extra_physical_rows" in query else list(self.findings))


def test_duplicate_audit_separates_physical_duplicates_and_identity_conflicts() -> None:
    occurred_at = datetime(2026, 7, 12, tzinfo=UTC)
    client = FakeClient(
        summary=(2, 3, 1),
        findings=(
            ("018ff8f4-86de-7b25-9b8a-2d22f6a3e001", 3, 2, occurred_at, occurred_at),
            ("018ff8f4-86de-7b25-9b8a-2d22f6a3e002", 2, 1, occurred_at, occurred_at),
        ),
    )

    audit = audit_event_duplicates(client, limit=2)

    assert audit.as_dict() == {
        "duplicateEventIds": 2,
        "extraPhysicalRows": 3,
        "conflictingEventIds": 1,
        "truncated": False,
        "findings": [
            {
                "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e001",
                "physicalRowCount": 3,
                "identityCount": 2,
                "firstOccurredAt": "2026-07-12T00:00:00.000Z",
                "lastOccurredAt": "2026-07-12T00:00:00.000Z",
            },
            {
                "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e002",
                "physicalRowCount": 2,
                "identityCount": 1,
                "firstOccurredAt": "2026-07-12T00:00:00.000Z",
                "lastOccurredAt": "2026-07-12T00:00:00.000Z",
            },
        ],
    }
    assert client.queries[1][1] == {"limit": 2}


def test_duplicate_audit_skips_detail_query_when_clean() -> None:
    client = FakeClient(summary=(0, 0, 0))

    audit = audit_event_duplicates(client)

    assert audit.as_dict()["findings"] == []
    assert len(client.queries) == 1


@pytest.mark.parametrize("limit", [0, 10_001])
def test_duplicate_audit_bounds_the_detail_limit(limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 10000"):
        audit_event_duplicates(FakeClient(summary=(0, 0, 0)), limit=limit)
