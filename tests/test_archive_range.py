from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.contracts.archives import ArchiveRestoreRequest
from backend.contracts.requests import (
    ArchiveRestoreListQuery,
    CorrelationQuery,
    EndpointListQuery,
    TopologyQuery,
)

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


def test_endpoint_id_lists_are_deduplicated_and_bounded() -> None:
    cases = [
        (ArchiveRestoreRequest, {"endpointIds": [1, 1, 2], "from": NOW, "to": NOW + timedelta(days=1)}),
        (ArchiveRestoreListQuery, {"endpointIds": [1, 1, 2], "from": NOW, "to": NOW + timedelta(days=1)}),
        (EndpointListQuery, {"endpointIds": [1, 1, 2]}),
        (TopologyQuery, {"endpointIds": [1, 1, 2]}),
        (CorrelationQuery, {"value": "example.com", "endpointIds": [1, 1, 2]}),
    ]
    for model, values in cases:
        assert model.model_validate(values).endpoint_ids == [1, 2]
        with pytest.raises(ValidationError):
            model.model_validate({**values, "endpointIds": list(range(1, 102))})
