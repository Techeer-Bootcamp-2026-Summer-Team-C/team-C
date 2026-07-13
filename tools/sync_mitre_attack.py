from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parents[1]
ATTACK_VERSION = "19.1"
SOURCE_URL = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/"
    "v19.1/enterprise-attack/enterprise-attack-19.1.json"
)
SOURCE_SHA256 = "bdf1ce86a4e604214c5076d37ae4dcb322678afc528df8492e6fdc1b554f5da3"
OUTPUT_PATH = ROOT / "mappings" / "mitre_attack.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the compact Enterprise ATT&CK catalog used by RuleV1 validation."
    )
    parser.add_argument("--source", default=SOURCE_URL, help="Pinned STIX JSON URL or local file path.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--expected-sha256", default=SOURCE_SHA256)
    return parser


def read_source(source: str) -> tuple[bytes, str]:
    if source.startswith(("https://", "http://")):
        request = urllib.request.Request(source, headers={"User-Agent": "EDR-C-MITRE-sync/1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read(), source
    path = Path(source).resolve()
    return path.read_bytes(), SOURCE_URL


def build_catalog(bundle: dict[str, Any], *, source_url: str, source_sha256: str) -> dict[str, Any]:
    objects = bundle.get("objects")
    if not isinstance(objects, list):
        raise ValueError("ATT&CK STIX bundle has no objects array")

    tactic_objects = [
        item for item in objects if item.get("type") == "x-mitre-tactic" and _is_active(item)
    ]
    tactic_codes_by_shortname: dict[str, str] = {}
    tactics: dict[str, dict[str, str]] = {}
    for item in tactic_objects:
        code = _external_id(item, prefix="TA")
        shortname = _required_string(item, "x_mitre_shortname")
        tactic_codes_by_shortname[shortname] = code
        tactics[code] = {"name": _required_string(item, "name"), "shortname": shortname}

    techniques: dict[str, dict[str, Any]] = {}
    for item in objects:
        if item.get("type") != "attack-pattern" or not _is_active(item):
            continue
        code = _external_id(item, prefix="T", required=False)
        if code is None:
            continue
        tactic_codes = sorted(
            {
                tactic_codes_by_shortname[phase["phase_name"]]
                for phase in item.get("kill_chain_phases", [])
                if phase.get("kill_chain_name") == "mitre-attack"
                and phase.get("phase_name") in tactic_codes_by_shortname
            }
        )
        if not tactic_codes:
            raise ValueError(f"active Enterprise ATT&CK technique has no tactic relationship: {code}")
        techniques[code] = {
            "name": _required_string(item, "name"),
            "tactic_codes": tactic_codes,
            "is_subtechnique": bool(item.get("x_mitre_is_subtechnique", False)),
        }

    if not tactics or not techniques:
        raise ValueError("ATT&CK STIX bundle produced an empty catalog")
    return {
        "schema_version": 2,
        "domain": "enterprise-attack",
        "attack_version": ATTACK_VERSION,
        "source": {
            "url": source_url,
            "sha256": source_sha256,
            "bundle_id": bundle.get("id", ""),
        },
        "tactics": dict(sorted(tactics.items())),
        "techniques": dict(sorted(techniques.items())),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_bytes, source_url = read_source(args.source)
    actual_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if actual_sha256.lower() != args.expected_sha256.lower():
        raise ValueError(
            f"ATT&CK source SHA-256 mismatch: expected {args.expected_sha256}, got {actual_sha256}"
        )
    bundle = json.loads(source_bytes)
    catalog = build_catalog(bundle, source_url=source_url, source_sha256=actual_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} with {len(catalog['tactics'])} tactics and "
        f"{len(catalog['techniques'])} techniques"
    )
    return 0


def _is_active(item: dict[str, Any]) -> bool:
    return not item.get("revoked", False) and not item.get("x_mitre_deprecated", False)


def _external_id(item: dict[str, Any], *, prefix: str, required: bool = True) -> str | None:
    for reference in item.get("external_references", []):
        external_id = reference.get("external_id")
        if reference.get("source_name") == "mitre-attack" and isinstance(external_id, str):
            if external_id.startswith(prefix):
                return external_id
    if required:
        raise ValueError(f"ATT&CK object has no {prefix} external ID: {item.get('id')}")
    return None


def _required_string(item: dict[str, Any], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"ATT&CK object {item.get('id')} has no {field}")
    return value.strip()


if __name__ == "__main__":
    raise SystemExit(main())
