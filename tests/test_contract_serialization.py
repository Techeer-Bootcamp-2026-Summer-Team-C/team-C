import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.contracts.common import ErrorEnvelope, SuccessEnvelope
from backend.contracts.endpoints import EndpointDetailDto
from backend.contracts.events import EventDetailDto

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("endpoint_detail_response.json", SuccessEnvelope[EndpointDetailDto]),
        ("event_detail_response.json", SuccessEnvelope[EventDetailDto]),
        ("error_response.json", ErrorEnvelope),
    ],
)
def test_fixtures_round_trip_with_camel_case(name: str, model: type) -> None:
    fixture = load_fixture(name)
    parsed = model.model_validate(fixture)
    assert parsed.model_dump(mode="json", by_alias=True) == fixture


def test_nullable_keys_and_empty_lists_are_not_omitted() -> None:
    parsed = SuccessEnvelope[EndpointDetailDto].model_validate(load_fixture("endpoint_detail_response.json"))
    dumped = parsed.model_dump(mode="json", by_alias=True)
    data = dumped["data"]
    assert "lastSeenAt" in data and data["lastSeenAt"] is None
    assert data["capabilityCodes"] == []
    assert data["sensorHealth"] == []
    assert data["risk"]["riskFactors"] == []
    assert data["certificates"] == []


def test_required_nullable_key_cannot_be_omitted() -> None:
    fixture = load_fixture("endpoint_detail_response.json")
    del fixture["data"]["lastSeenAt"]  # type: ignore[index]
    with pytest.raises(ValidationError):
        SuccessEnvelope[EndpointDetailDto].model_validate(fixture)


def test_unknown_response_key_is_rejected() -> None:
    fixture = load_fixture("error_response.json")
    fixture["unexpected"] = True
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate(fixture)
