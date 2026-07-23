import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from backend.rule_loader import RuleLoader
from backend.rules import RuleV1

ROOT = Path(__file__).parents[1]
SCHEMA_PATH = ROOT / "schemas" / "rule-v1.schema.json"
RULE_PATH = ROOT / "rules" / "process" / "proc_powershell_encoded.v2.yaml"
ACTIVE_RULE_IDENTITIES = {
    ("PROC_POWERSHELL_ENCODED", 2),
    ("NET_SUSPICIOUS_EGRESS", 2),
    ("DNS_RARE_DOMAIN", 2),
    ("FILE_SUSPICIOUS_DROP", 2),
    ("L7_UPLOAD_ANOMALY", 2),
}


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


def test_all_active_rule_versions_load_with_response_guidance() -> None:
    loader = RuleLoader(
        schema_path=SCHEMA_PATH,
        mapping_path=ROOT / "mappings" / "mitre_attack.yaml",
    )
    loaded = loader.load_directory(ROOT / "rules")
    by_identity = {(item.rule.rule_code, item.rule.version): item.rule for item in loaded}
    active_identities = {identity for identity, rule in by_identity.items() if rule.enabled}

    assert ACTIVE_RULE_IDENTITIES == active_identities
    for identity in ACTIVE_RULE_IDENTITIES:
        guidance = by_identity[identity].response_guidance
        assert guidance
        assert [step.order for step in guidance] == list(range(1, len(guidance) + 1))


def test_historical_rule_versions_are_disabled_but_keep_alert_guidance() -> None:
    loader = RuleLoader(
        schema_path=SCHEMA_PATH,
        mapping_path=ROOT / "mappings" / "mitre_attack.yaml",
    )
    loaded = loader.load_directory(ROOT / "rules")
    historical = [item.rule for item in loaded if item.rule.version == 1]

    assert {rule.rule_code for rule in historical} == {code for code, _version in ACTIVE_RULE_IDENTITIES}
    assert all(not rule.enabled for rule in historical)
    assert all(not rule.incident.enabled for rule in historical)
    assert all(rule.response_guidance for rule in historical)


def test_cross_rule_correlation_requires_explicit_shared_key_and_window() -> None:
    loader = RuleLoader(
        schema_path=SCHEMA_PATH,
        mapping_path=ROOT / "mappings" / "mitre_attack.yaml",
    )
    loaded = loader.load_directory(ROOT / "rules")
    incidents = {
        item.rule.rule_code: item.rule.incident
        for item in loaded
        if item.rule.enabled and item.rule.incident.enabled
    }

    process = incidents["PROC_POWERSHELL_ENCODED"]
    egress = incidents["NET_SUSPICIOUS_EGRESS"]
    assert process.correlation_key == egress.correlation_key == "powershell-tls-egress-chain"
    assert process.window_seconds == egress.window_seconds == 1800
    assert all(
        incident.correlation_key != process.correlation_key
        for code, incident in incidents.items()
        if code not in {"PROC_POWERSHELL_ENCODED", "NET_SUSPICIOUS_EGRESS"}
    )


def test_rule_semantics_use_collected_fields_and_compatible_mitre_mappings() -> None:
    loader = RuleLoader(
        schema_path=SCHEMA_PATH,
        mapping_path=ROOT / "mappings" / "mitre_attack.yaml",
    )
    rules = {
        item.rule.rule_code: item.rule
        for item in loader.load_directory(ROOT / "rules")
        if item.rule.enabled
    }

    egress = rules["NET_SUSPICIOUS_EGRESS"]
    assert egress.event_type.value == "L7_EVENT"
    assert {condition.field for condition in egress.conditions.all} == {"l7_protocol", "tls_sni"}
    assert egress.mitre is not None
    assert egress.mitre.technique_code == "T1573"

    file_rule = rules["FILE_SUSPICIOUS_DROP"]
    assert file_rule.mitre is not None
    assert file_rule.mitre.tactic_code == "TA0011"
    assert file_rule.mitre.technique_code == "T1105"

    upload = rules["L7_UPLOAD_ANOMALY"]
    protocol = next(condition for condition in upload.conditions.all if condition.field == "l7_protocol")
    assert protocol.operator == "eq"
    assert protocol.value == "HTTP"
    assert upload.mitre is not None
    assert upload.mitre.technique_code == "T1048.003"


def test_enabled_rule_condition_field_must_exist_for_event_type(tmp_path: Path) -> None:
    loader = RuleLoader(
        schema_path=SCHEMA_PATH,
        mapping_path=ROOT / "mappings" / "mitre_attack.yaml",
    )
    rule = load_rule()
    rule["conditions"]["all"][0]["field"] = "remote_ip"
    path = tmp_path / "invalid-field.yaml"
    path.write_text(yaml.safe_dump(rule), encoding="utf-8")

    with pytest.raises(ValueError, match="condition fields unavailable for PROCESS_EXECUTION: remote_ip"):
        loader.load_file(path)


def test_shared_correlation_key_requires_one_window_size(tmp_path: Path) -> None:
    loader = RuleLoader(
        schema_path=SCHEMA_PATH,
        mapping_path=ROOT / "mappings" / "mitre_attack.yaml",
    )
    process = load_rule()
    egress = yaml.safe_load(
        (ROOT / "rules" / "network" / "net_suspicious_egress.v2.yaml").read_text(encoding="utf-8")
    )
    egress["incident"]["window_seconds"] = 900
    (tmp_path / "process.yaml").write_text(yaml.safe_dump(process), encoding="utf-8")
    (tmp_path / "egress.yaml").write_text(yaml.safe_dump(egress), encoding="utf-8")

    with pytest.raises(ValueError, match="has inconsistent window_seconds"):
        loader.load_directory(tmp_path)


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
