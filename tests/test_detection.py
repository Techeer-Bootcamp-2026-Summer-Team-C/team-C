from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.detection import DetectionEngine
from backend.rule_loader import RuleLoader

ROOT = Path(__file__).parents[1]


def test_rule_loader_and_detection_snapshot_rule_strings() -> None:
    loader = RuleLoader(
        schema_path=ROOT / "schemas/rule-v1.schema.json",
        mapping_path=ROOT / "mappings/mitre_attack.yaml",
    )
    loaded = loader.load_directory(ROOT / "rules")
    engine = DetectionEngine(loaded)
    occurred_at = datetime(2026, 7, 12, 1, 2, 3, tzinfo=UTC)
    matches = engine.evaluate(
        {
            "event_id": "018ff8f4-86de-7b25-9b8a-2d22f6a3e001",
            "batch_id": "018ff8f4-86de-7b25-9b8a-2d22f6a3e000",
            "endpoint_id": 1001,
            "agent_id": "agent-win-001",
            "event_type": "PROCESS_EXECUTION",
            "occurred_at": occurred_at,
            "process_name": "powershell.exe",
            "command_line": "powershell.exe -EncodedCommand ZQBjAGgAbwA=",
        },
        detected_at=occurred_at,
    )
    assert len(matches) == 1
    alert = matches[0].alert
    assert alert.rule_name == "PowerShell Encoded Command"
    assert alert.title == "Encoded PowerShell command detected"
    assert alert.summary == "PowerShell was executed with an encoded command argument."
    assert alert.mitre_tactic_name == "Execution"
    assert matches[0].incident is not None
    assert matches[0].incident.correlation_key == "powershell-tls-egress-chain"


def test_non_matching_event_does_not_create_alert() -> None:
    loader = RuleLoader(
        schema_path=ROOT / "schemas/rule-v1.schema.json",
        mapping_path=ROOT / "mappings/mitre_attack.yaml",
    )
    engine = DetectionEngine(loader.load_directory(ROOT / "rules"))
    matches = engine.evaluate(
        {
            "event_id": "018ff8f4-86de-7b25-9b8a-2d22f6a3e002",
            "endpoint_id": 1001,
            "agent_id": "agent-win-001",
            "event_type": "PROCESS_EXECUTION",
            "occurred_at": datetime(2026, 7, 12, tzinfo=UTC),
            "command_line": "notepad.exe",
        },
        detected_at=datetime(2026, 7, 12, tzinfo=UTC),
    )
    assert matches == []


@pytest.mark.parametrize(
    ("event_type", "fields", "expected_rule_code"),
    [
        (
            "L7_EVENT",
            {"l7_protocol": "TLS", "tls_sni": "update-cache.example.net"},
            "NET_SUSPICIOUS_EGRESS",
        ),
        (
            "FILE_EVENT",
            {"file_action": "CREATE", "file_path": r"C:\ProgramData\cache\payload-demo.bin"},
            "FILE_SUSPICIOUS_DROP",
        ),
        (
            "DNS_QUERY",
            {"dns_query": "rare-beacon.example.net"},
            "DNS_RARE_DOMAIN",
        ),
        (
            "L7_EVENT",
            {"l7_protocol": "HTTP", "http_method": "POST", "http_host": "storage.example.com"},
            "L7_UPLOAD_ANOMALY",
        ),
    ],
)
def test_demo_rule_matches_seeded_source_event(
    event_type: str,
    fields: dict[str, object],
    expected_rule_code: str,
) -> None:
    loader = RuleLoader(
        schema_path=ROOT / "schemas/rule-v1.schema.json",
        mapping_path=ROOT / "mappings/mitre_attack.yaml",
    )
    engine = DetectionEngine(loader.load_directory(ROOT / "rules"))
    occurred_at = datetime(2026, 7, 12, 1, 2, 3, tzinfo=UTC)
    matches = engine.evaluate(
        {
            "event_id": "018ff8f4-86de-7b25-9b8a-2d22f6a3e100",
            "batch_id": "018ff8f4-86de-7b25-9b8a-2d22f6a3e000",
            "endpoint_id": 1001,
            "agent_id": "agent-win-001",
            "event_type": event_type,
            "occurred_at": occurred_at,
            **fields,
        },
        detected_at=occurred_at,
    )

    assert [match.alert.rule_code for match in matches] == [expected_rule_code]


def test_powershell_and_tls_egress_share_only_the_configured_endpoint_window() -> None:
    loader = RuleLoader(
        schema_path=ROOT / "schemas/rule-v1.schema.json",
        mapping_path=ROOT / "mappings/mitre_attack.yaml",
    )
    engine = DetectionEngine(loader.load_directory(ROOT / "rules"))
    process_time = datetime(2026, 7, 12, 1, 2, 3, tzinfo=UTC)
    egress_time = datetime(2026, 7, 12, 1, 12, 3, tzinfo=UTC)
    process = engine.evaluate(
        {
            "event_id": "018ff8f4-86de-7b25-9b8a-2d22f6a3e201",
            "endpoint_id": 1001,
            "agent_id": "agent-win-001",
            "event_type": "PROCESS_EXECUTION",
            "occurred_at": process_time,
            "process_name": "powershell.exe",
            "command_line": "powershell.exe -EncodedCommand [REDACTED]",
        },
        detected_at=process_time,
    )[0]
    egress = engine.evaluate(
        {
            "event_id": "018ff8f4-86de-7b25-9b8a-2d22f6a3e202",
            "endpoint_id": 1001,
            "agent_id": "agent-win-001",
            "event_type": "L7_EVENT",
            "occurred_at": egress_time,
            "l7_protocol": "TLS",
            "tls_sni": "update-cache.example.net",
        },
        detected_at=egress_time,
    )[0]

    assert process.alert.rule_code == "PROC_POWERSHELL_ENCODED"
    assert egress.alert.rule_code == "NET_SUSPICIOUS_EGRESS"
    assert process.incident is not None
    assert egress.incident is not None
    assert process.incident.endpoint_id == egress.incident.endpoint_id == 1001
    assert process.incident.correlation_key == egress.incident.correlation_key
    assert process.incident.window_start_at == egress.incident.window_start_at
    assert process.incident.window_end_at == egress.incident.window_end_at


def test_https_metadata_does_not_claim_unencrypted_upload_technique() -> None:
    loader = RuleLoader(
        schema_path=ROOT / "schemas/rule-v1.schema.json",
        mapping_path=ROOT / "mappings/mitre_attack.yaml",
    )
    engine = DetectionEngine(loader.load_directory(ROOT / "rules"))
    occurred_at = datetime(2026, 7, 12, 1, 2, 3, tzinfo=UTC)
    matches = engine.evaluate(
        {
            "event_id": "018ff8f4-86de-7b25-9b8a-2d22f6a3e203",
            "endpoint_id": 1001,
            "agent_id": "agent-win-001",
            "event_type": "L7_EVENT",
            "occurred_at": occurred_at,
            "l7_protocol": "HTTPS",
            "http_method": "POST",
            "http_host": "storage.example.com",
        },
        detected_at=occurred_at,
    )

    assert matches == []
