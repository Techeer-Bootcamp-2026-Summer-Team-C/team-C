from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.errors import EventIdentityConflictError
from backend.storage.clickhouse import EVENT_COLUMNS, EventRepository

EVENT_ID = UUID("018ff8f4-86de-7b25-9b8a-2d22f6a3f001")


class Client:
    def __init__(self, rows=()) -> None:
        self.rows = list(rows)
        self.inserts: list[tuple[str, list[list[object]], list[str]]] = []
        self.last_query = ""

    def query(self, query, parameters=None):
        self.last_query = query
        return SimpleNamespace(result_rows=self.rows)

    def insert(self, table, data, column_names):
        self.inserts.append((table, data, column_names))


def test_event_repository_is_read_only_unless_write_intent_is_explicit() -> None:
    client = Client()

    with pytest.raises(PermissionError, match="read-only"):
        EventRepository(client).insert([{"event_id": EVENT_ID}])

    EventRepository.for_ingest(client).insert([{"event_id": EVENT_ID}])
    assert client.inserts == [("edr_events", [[EVENT_ID] + [None] * (len(EVENT_COLUMNS) - 1)], EVENT_COLUMNS)]


def test_only_ingest_mode_is_valid_for_event_storage_worker() -> None:
    client = Client()

    EventRepository.for_ingest(client).assert_ingest_writer()
    for repository in (EventRepository(client), EventRepository.for_maintenance(client)):
        with pytest.raises(RuntimeError, match=r"requires EventRepository\.for_ingest\(\)"):
            repository.assert_ingest_writer()


def test_event_identity_reads_all_physical_identities_and_rejects_ambiguity() -> None:
    unique = Client(rows=[(1001, "agent-001", b"a" * 64)])

    identity = EventRepository(unique).identity(EVENT_ID)

    assert identity is not None
    assert identity.event_id == EVENT_ID
    assert identity.endpoint_id == 1001
    assert identity.payload_sha256 == "a" * 64
    assert "FINAL" not in unique.last_query
    assert "LIMIT 2" in unique.last_query

    conflicting = Client(rows=[(1001, "agent-001", b"a" * 64), (1001, "agent-001", b"b" * 64)])
    with pytest.raises(EventIdentityConflictError, match="multiple physical identities"):
        EventRepository(conflicting).identity(EVENT_ID)
