import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from backend.rules import RuleV1

ROOT = Path(__file__).parents[1]
SCHEMA_PATH = ROOT / "schemas" / "rule-v1.schema.json"
RULE_PATH = ROOT / "rules" / "process" / "proc_powershell_encoded.v1.yaml"


def load_rule() -> dict[str, object]:
    return yaml.safe_load(RULE_PATH.read_text(encoding="utf-8"))


def test_sample_rule_matches_json_schema_and_pydantic_model() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    rule = load_rule()
    Draft202012Validator(schema).validate(rule)
    parsed = RuleV1.model_validate(rule)
    assert parsed.rule_code == "PROC_POWERSHELL_ENCODED"
    assert parsed.rule_name == "PowerShell Encoded Command"
    assert parsed.alert_title == "Encoded PowerShell command detected"
    assert parsed.response_guidance[0].requires_manual_action is False


def test_enabled_rule_requires_mitre_codes() -> None:
    rule = load_rule()
    del rule["mitre"]
    with pytest.raises(ValidationError):
        RuleV1.model_validate(rule)


@pytest.mark.parametrize(
    ("field", "value"),
    [("tactic_code", "Execution"), ("technique_code", "T1059.1"), ("technique_code", "TA0002")],
)
def test_mitre_codes_require_attack_external_id_format(field: str, value: str) -> None:
    rule = load_rule()
    rule["mitre"][field] = value
    with pytest.raises(ValidationError):
        RuleV1.model_validate(rule)


def test_response_guidance_order_must_be_unique() -> None:
    rule = load_rule()
    first = dict(rule["response_guidance"][0])
    rule["response_guidance"].append(first)
    with pytest.raises(ValidationError):
        RuleV1.model_validate(rule)


def test_disabled_rule_omits_mitre_and_incident_fields() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    rule = load_rule()
    rule["enabled"] = False
    rule.pop("mitre")
    rule["incident"] = {"enabled": False}
    Draft202012Validator(schema).validate(rule)
    parsed = RuleV1.model_validate(rule)
    assert parsed.mitre is None
    assert parsed.incident.correlation_key is None
    assert parsed.incident.window_seconds is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rule: rule.update({"enabled": False, "mitre": None}),
        lambda rule: rule.update({"enabled": False, "incident": {"enabled": False, "correlation_key": None}}),
        lambda rule: rule.update({"enabled": False, "incident": {"enabled": False, "window_seconds": None}}),
    ],
)
def test_disabled_rule_rejects_null_instead_of_omission(mutate) -> None:
    rule = load_rule()
    rule.pop("mitre", None)
    rule["incident"] = {"enabled": False}
    mutate(rule)
    with pytest.raises((ValidationError, JsonSchemaValidationError)):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(rule)
        RuleV1.model_validate(rule)
