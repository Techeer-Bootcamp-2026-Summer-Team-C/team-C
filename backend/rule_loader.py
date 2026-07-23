import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .contracts.enums import EventType
from .mitre import load_mitre_catalog
from .rules import RuleV1

CONDITION_FIELDS_BY_EVENT_TYPE: dict[EventType, frozenset[str]] = {
    EventType.PROCESS_EXECUTION: frozenset(
        {
            "process_name",
            "process_path",
            "pid",
            "ppid",
            "command_line",
            "user_name",
        }
    ),
    EventType.NETWORK_CONNECTION: frozenset(
        {
            "protocol",
            "remote_ip",
            "remote_port",
            "remote_domain",
            "process_name",
            "pid",
        }
    ),
    EventType.FILE_EVENT: frozenset(
        {
            "file_path",
            "file_action",
            "file_hash_sha256",
            "process_name",
            "pid",
        }
    ),
    EventType.DNS_QUERY: frozenset(
        {
            "dns_query",
            "dns_record_type",
            "dns_response_code",
            "dns_answers_json",
            "process_name",
            "pid",
        }
    ),
    EventType.L7_EVENT: frozenset(
        {
            "l7_protocol",
            "http_method",
            "http_host",
            "url",
            "http_status_code",
            "http_user_agent",
            "tls_sni",
            "tls_version",
            "tls_certificate_subject",
            "tls_certificate_issuer",
            "tls_certificate_sha256",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class LoadedRule:
    rule: RuleV1
    tactic_name: str | None
    technique_name: str | None
    source_path: Path


class RuleLoader:
    def __init__(self, *, schema_path: Path, mapping_path: Path) -> None:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.validator = Draft202012Validator(schema)
        self.catalog = load_mitre_catalog(mapping_path)

    def load_file(self, path: Path) -> LoadedRule:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.validator.validate(raw)
        rule = RuleV1.model_validate(raw)
        for condition in rule.conditions.all:
            if condition.operator == "regex":
                re.compile(str(condition.value))
        if not rule.enabled:
            return LoadedRule(rule, None, None, path)
        allowed_fields = CONDITION_FIELDS_BY_EVENT_TYPE[rule.event_type]
        invalid_fields = sorted({condition.field for condition in rule.conditions.all} - allowed_fields)
        if invalid_fields:
            raise ValueError(
                f"enabled rule {rule.rule_code} v{rule.version} has condition fields unavailable "
                f"for {rule.event_type.value}: {', '.join(invalid_fields)}"
            )
        if rule.mitre is None:
            raise ValueError(f"enabled rule {rule.rule_code} has no MITRE mapping")
        try:
            tactic_name, technique_name = self.catalog.resolve(
                tactic_code=rule.mitre.tactic_code,
                technique_code=rule.mitre.technique_code,
            )
        except ValueError as error:
            raise ValueError(f"invalid MITRE mapping for {rule.rule_code} v{rule.version}: {error}") from error
        return LoadedRule(rule, tactic_name, technique_name, path)

    def load_directory(self, root: Path) -> list[LoadedRule]:
        loaded = [self.load_file(path) for path in sorted(root.rglob("*.yaml"))]
        identities = [(item.rule.rule_code, item.rule.version) for item in loaded]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate rule_code/version")
        enabled_codes = [item.rule.rule_code for item in loaded if item.rule.enabled]
        if len(enabled_codes) != len(set(enabled_codes)):
            raise ValueError("multiple enabled versions for rule_code")
        correlation_windows: dict[str, int] = {}
        for item in loaded:
            incident = item.rule.incident
            if not item.rule.enabled or not incident.enabled:
                continue
            if incident.correlation_key is None or incident.window_seconds is None:
                raise RuntimeError("enabled incident was not model-validated")
            existing = correlation_windows.setdefault(incident.correlation_key, incident.window_seconds)
            if existing != incident.window_seconds:
                raise ValueError(
                    f"correlation_key {incident.correlation_key!r} has inconsistent window_seconds: "
                    f"{existing} and {incident.window_seconds}"
                )
        return loaded
