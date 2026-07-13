from pathlib import Path

import pytest

from backend.mitre import load_mitre_catalog
from backend.rule_loader import RuleLoader

ROOT = Path(__file__).parents[1]
CATALOG_PATH = ROOT / "mappings" / "mitre_attack.yaml"


def test_generated_catalog_has_full_active_enterprise_matrix() -> None:
    catalog = load_mitre_catalog(CATALOG_PATH)
    assert catalog.domain == "enterprise-attack"
    assert catalog.attack_version == "19.1"
    assert catalog.source_url.endswith("/enterprise-attack-19.1.json")
    assert len(catalog.source_sha256) == 64
    assert catalog.bundle_id.startswith("bundle--")
    assert len(catalog.tactics) == 15
    assert len(catalog.techniques) == 697
    assert catalog.tactics["TA0002"] == "Execution"
    assert catalog.techniques["T1059.001"].name == "PowerShell"
    assert "TA0002" in catalog.techniques["T1059.001"].tactic_codes


def test_catalog_rejects_invalid_tactic_technique_pair() -> None:
    catalog = load_mitre_catalog(CATALOG_PATH)
    with pytest.raises(ValueError, match="does not belong"):
        catalog.resolve(tactic_code="TA0001", technique_code="T1059.001")


def test_rule_loader_rejects_existing_codes_in_an_invalid_pair(tmp_path: Path) -> None:
    rule_path = tmp_path / "invalid_pair.yaml"
    sample = (ROOT / "rules" / "process" / "proc_powershell_encoded.v1.yaml").read_text(encoding="utf-8")
    rule_path.write_text(sample.replace("tactic_code: TA0002", "tactic_code: TA0001"), encoding="utf-8")
    loader = RuleLoader(
        schema_path=ROOT / "schemas" / "rule-v1.schema.json",
        mapping_path=CATALOG_PATH,
    )
    with pytest.raises(ValueError, match="does not belong"):
        loader.load_file(rule_path)
