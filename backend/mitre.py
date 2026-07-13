from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

TACTIC_CODE_PATTERN = r"^TA\d{4}$"
TECHNIQUE_CODE_PATTERN = r"^T\d{4}(?:\.\d{3})?$"

_TACTIC_CODE_RE = re.compile(TACTIC_CODE_PATTERN)
_TECHNIQUE_CODE_RE = re.compile(TECHNIQUE_CODE_PATTERN)


@dataclass(frozen=True, slots=True)
class MitreTechnique:
    name: str
    tactic_codes: frozenset[str]
    is_subtechnique: bool


@dataclass(frozen=True, slots=True)
class MitreCatalog:
    domain: str
    attack_version: str
    source_url: str
    source_sha256: str
    bundle_id: str
    tactics: dict[str, str]
    techniques: dict[str, MitreTechnique]

    def resolve(self, *, tactic_code: str, technique_code: str) -> tuple[str, str]:
        tactic_name = self.tactics.get(tactic_code)
        technique = self.techniques.get(technique_code)
        if tactic_name is None or technique is None:
            raise ValueError(f"unknown MITRE ATT&CK mapping: {tactic_code}/{technique_code}")
        if tactic_code not in technique.tactic_codes:
            raise ValueError(
                f"MITRE ATT&CK technique {technique_code} does not belong to tactic {tactic_code}"
            )
        return tactic_name, technique.name


def load_mitre_catalog(path: Path) -> MitreCatalog:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("MITRE ATT&CK catalog must be a YAML object")
    if raw.get("schema_version") != 2:
        raise ValueError("MITRE ATT&CK catalog schema_version must be 2")
    domain = _required_string(raw, "domain")
    attack_version = _required_string(raw, "attack_version")
    if domain != "enterprise-attack":
        raise ValueError(f"unsupported MITRE ATT&CK domain: {domain}")
    source = _required_mapping(raw, "source")
    source_url = _required_string(source, "url")
    source_sha256 = _required_string(source, "sha256")
    bundle_id = _required_string(source, "bundle_id")
    if re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None:
        raise ValueError("MITRE ATT&CK catalog source sha256 must be lowercase hexadecimal")
    if not bundle_id.startswith("bundle--"):
        raise ValueError("MITRE ATT&CK catalog source bundle_id is invalid")

    tactic_rows = _required_mapping(raw, "tactics")
    technique_rows = _required_mapping(raw, "techniques")

    tactics: dict[str, str] = {}
    for code, value in tactic_rows.items():
        if not isinstance(code, str) or _TACTIC_CODE_RE.fullmatch(code) is None:
            raise ValueError(f"invalid MITRE ATT&CK tactic code: {code}")
        if not isinstance(value, dict):
            raise ValueError(f"MITRE ATT&CK tactic {code} must be an object")
        tactics[code] = _required_string(value, "name")

    techniques: dict[str, MitreTechnique] = {}
    for code, value in technique_rows.items():
        if not isinstance(code, str) or _TECHNIQUE_CODE_RE.fullmatch(code) is None:
            raise ValueError(f"invalid MITRE ATT&CK technique code: {code}")
        if not isinstance(value, dict):
            raise ValueError(f"MITRE ATT&CK technique {code} must be an object")
        tactic_codes_raw = value.get("tactic_codes")
        if not isinstance(tactic_codes_raw, list) or not tactic_codes_raw:
            raise ValueError(f"MITRE ATT&CK technique {code} must have tactic_codes")
        tactic_codes = frozenset(tactic_codes_raw)
        if len(tactic_codes) != len(tactic_codes_raw):
            raise ValueError(f"MITRE ATT&CK technique {code} has duplicate tactic_codes")
        unknown_tactics = tactic_codes - tactics.keys()
        if unknown_tactics:
            raise ValueError(f"MITRE ATT&CK technique {code} has unknown tactics: {sorted(unknown_tactics)}")
        is_subtechnique = value.get("is_subtechnique")
        if not isinstance(is_subtechnique, bool):
            raise ValueError(f"MITRE ATT&CK technique {code} must declare is_subtechnique")
        techniques[code] = MitreTechnique(
            name=_required_string(value, "name"),
            tactic_codes=tactic_codes,
            is_subtechnique=is_subtechnique,
        )

    return MitreCatalog(
        domain=domain,
        attack_version=attack_version,
        source_url=source_url,
        source_sha256=source_sha256,
        bundle_id=bundle_id,
        tactics=tactics,
        techniques=techniques,
    )


def _required_mapping(raw: dict[str, Any], field: str) -> dict[str, Any]:
    value = raw.get(field)
    if not isinstance(value, dict) or not value:
        raise ValueError(f"MITRE ATT&CK catalog {field} must be a non-empty object")
    return value


def _required_string(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"MITRE ATT&CK catalog {field} must be a non-empty string")
    return value.strip()
