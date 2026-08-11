from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.storage.postgres import EventIngestRegistryRepository


class Connection:
    def __init__(self, row: tuple[bool, ...]) -> None:
        self.row = row

    @contextmanager
    def transaction(self):
        yield

    def execute(self, _query):
        return SimpleNamespace(fetchone=lambda: self.row)


def test_registry_preflight_requires_partition_and_trigger_contract() -> None:
    EventIngestRegistryRepository(Connection((True,) * 8)).assert_ready()

    missing_partition_trigger = (True, True, True, True, True, True, True, False)
    with pytest.raises(RuntimeError, match="partition truncate triggers"):
        EventIngestRegistryRepository(Connection(missing_partition_trigger)).assert_ready()
