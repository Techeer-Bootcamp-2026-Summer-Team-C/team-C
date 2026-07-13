import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .mitre import load_mitre_catalog
from .rules import RuleV1


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
        return loaded
