from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.contracts.archives import ArchiveRestoreRequest
from backend.contracts.requests import ArchiveRestoreListQuery

NOW = datetime(2026, 7, 12, tzinfo=UTC)


@pytest.mark.parametrize("model", [ArchiveRestoreRequest, ArchiveRestoreListQuery])
def test_archive_range_accepts_exactly_31_days(model: type) -> None:
    value = model.model_validate({"endpointIds": [1], "from": NOW, "to": NOW + timedelta(days=31)})
    assert value.to - value.from_ == timedelta(days=31)


@pytest.mark.parametrize("model", [ArchiveRestoreRequest, ArchiveRestoreListQuery])
@pytest.mark.parametrize("to", [NOW, NOW - timedelta(seconds=1), NOW + timedelta(days=31, milliseconds=1)])
def test_archive_range_rejects_invalid_or_too_long(model: type, to: datetime) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({"endpointIds": [1], "from": NOW, "to": to})
