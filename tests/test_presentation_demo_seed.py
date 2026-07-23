import json
import os
import tempfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from clickhouse_connect.driver.exceptions import ClickHouseError

from tools.seed_presentation_demo import (
    EndpointPlan,
    SeedTarget,
    _apply_clickhouse_down_file,
    _manifest_output_path,
    _preflight_manifest_output,
    _reset_databases,
    agent_fixture_metadata,
    assert_safe_reset_target,
    build_dns_correctness_plan,
    build_presentation_plan,
    main,
    parse_anchor,
    production_demo_fingerprint,
)
from tools.seed_safety import (
    PRODUCTION_DEMO_RESET_CONFIRMATION,
    PRODUCTION_RUNTIME_STOPPED_CONFIRMATION,
)

ANCHOR = datetime(2026, 7, 21, 12, 20, tzinfo=UTC)


def test_presentation_profile_has_exact_counts_distribution_and_correlation() -> None:
    plan = build_presentation_plan(20_260_721, ANCHOR)

    assert plan.counts == {"endpoints": 5, "events": 5_600, "alerts": 3, "incidents": 1}
    assert {endpoint.hostname: endpoint.event_count for endpoint in plan.endpoints} == {
        "GEONHA-MACMINI": 1_400,
        "GEONHA-WIN": 1_050,
        "SOYEON-WIN": 1_190,
        "HYERYEONG-WIN": 910,
        "JUHO-WIN": 1_050,
    }
    assert Counter(endpoint.owner_name for endpoint in plan.endpoints) == {
        "황건하": 2,
        "박소연": 1,
        "이혜령": 1,
        "이주호": 1,
    }
    assert {endpoint.major for endpoint in plan.endpoints if endpoint.owner_name == "이혜령"} == {"디자인전공"}
    assert {
        endpoint.major for endpoint in plan.endpoints if endpoint.owner_name != "이혜령"
    } == {"컴퓨터공학전공"}
    assert sum(event.occurred_at > ANCHOR - timedelta(days=1) for event in plan.events) == 400
    assert sum(event.occurred_at > ANCHOR - timedelta(days=7) for event in plan.events) == 2_800
    assert min(event.occurred_at for event in plan.events) > ANCHOR - timedelta(days=14)
    assert max(event.occurred_at for event in plan.events) <= ANCHOR
    assert {event.event_type for event in plan.events} == {
        "PROCESS_EXECUTION",
        "NETWORK_CONNECTION",
        "FILE_EVENT",
        "DNS_QUERY",
        "L7_EVENT",
    }
    powershell = [
        event
        for event in plan.events
        if event.event_type == "PROCESS_EXECUTION" and "-EncodedCommand" in str(event.payload.get("commandLine"))
    ]
    assert len(powershell) == 2
    assert {event.hostname for event in powershell} == {"SOYEON-WIN"}
    assert abs((powershell[1].occurred_at - powershell[0].occurred_at).total_seconds()) < 1_800
    tls_egress = [
        event
        for event in plan.events
        if event.hostname == "SOYEON-WIN"
        and event.event_type == "L7_EVENT"
        and event.payload.get("tlsSni") == "update-cache.test"
    ]
    assert len(tls_egress) == 1
    assert tls_egress[0].payload == {
        "l7Protocol": "TLS",
        "tlsSni": "update-cache.test",
        "tlsVersion": "TLS1.2",
    }
    minecraft = [
        event
        for event in plan.events
        if "Minecraft_Shader_Setup.exe" in json.dumps(event.payload, ensure_ascii=False)
    ]
    assert len(minecraft) == 2
    assert {event.hostname for event in minecraft} == {"SOYEON-WIN"}


def test_profile_generation_is_deterministic_for_seed_and_anchor() -> None:
    first = build_presentation_plan(7, ANCHOR)
    second = build_presentation_plan(7, ANCHOR)

    assert first.events == second.events
    assert len({event.event_id for event in first.events}) == 5_600
    assert len({event.batch_id for event in first.events}) == 5_600


def test_presentation_agent_metadata_matches_shipped_agent_contracts() -> None:
    endpoints = (
        EndpointPlan("MAC", "mac", "MACOS", "macOS 15.5", "192.0.2.1", "ONLINE", 1, "ARM64"),
        EndpointPlan("WIN", "win", "WINDOWS", "Windows 11 24H2", "192.0.2.2", "ONLINE", 1, "X64"),
        EndpointPlan(
            "WIN-DEGRADED",
            "win-degraded",
            "WINDOWS",
            "Windows 11 24H2",
            "192.0.2.3",
            "ONLINE",
            1,
            "X64",
            sensor_status="DEGRADED",
        ),
    )
    metadata = {endpoint.hostname: agent_fixture_metadata(endpoint) for endpoint in endpoints}

    assert {item.version for item in metadata.values()} == {"0.1.0"}
    assert metadata["MAC"].build_id == "macos-arm64-20260712.1"
    assert metadata["WIN"].build_id == "win-x64-20260712.1"
    assert metadata["MAC"].capability_codes == (
        "PROCESS_EXECUTION",
        "NETWORK_CONNECTION",
        "FILE_EVENT",
        "DNS_QUERY",
        "L7_EVENT",
        "PACKET_METADATA_V1",
    )
    assert metadata["WIN-DEGRADED"].capability_codes == (
        "PROCESS_EXECUTION",
        "NETWORK_CONNECTION",
        "FILE_EVENT",
        "DNS_QUERY",
    )
    assert {
        item.get("provider") for item in metadata["MAC"].sensor_health if item.get("provider")
    } == {"TCPDUMP"}
    assert {
        item.get("provider") for item in metadata["WIN"].sensor_health if item.get("provider")
    } == {"DNS_CLIENT_ETW", "NPCAP"}
    assert {
        item["status"]
        for item in metadata["WIN-DEGRADED"].sensor_health
        if item["sensor"] in {"PACKET_METADATA", "L7"}
    } == {"DEGRADED"}


def test_dns_correctness_fixture_contains_boundaries_and_exact_answer_members() -> None:
    plan = build_dns_correctness_plan(20_260_721, ANCHOR)
    serialized = json.dumps([event.payload for event in plan.events])

    assert plan.counts == {"endpoints": 2, "events": 8, "alerts": 0, "incidents": 0}
    values = (
        "yahoo.com",
        "mail.yahoo.com",
        "api.yahoo.com",
        "notyahoo.com",
        "yahoo.com.evil.example",
        "yahoo.co",
    )
    assert all(value in serialized for value in values)
    answers = [event.payload["answers"] for event in plan.events if "answers" in event.payload]
    assert ["203.0.113.10", "203.0.113.11"] in answers
    assert all("203.0.113.1" not in members for members in answers)


def test_dry_run_prints_counts_without_reset_confirmation(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "--profile",
                "presentation",
                "--seed",
                "1",
                "--anchor",
                "2026-07-21T12:20:00Z",
                "--dry-run",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Endpoints:        5" in output
    assert "Events:           5600" in output
    assert "Alerts:           3" in output
    assert "Incidents:        1" in output
    assert "mock data:        yes" in output


def test_anchor_requires_timezone() -> None:
    with pytest.raises(ValueError, match="UTC offset"):
        parse_anchor("2026-07-21T12:00:00")


@pytest.mark.parametrize(
    "target",
    [
        SeedTarget(
            "production",
            "postgresql://edr:x@127.0.0.1/edr",
            "http://edr:x@127.0.0.1/edr",
            "http://127.0.0.1:8080",
            "https://127.0.0.1:8443/api/v1/collector",
        ),
        SeedTarget(
            "local",
            "postgresql://edr:x@db.production.example/edr",
            "http://edr:x@127.0.0.1/edr",
            "http://127.0.0.1:8080",
            "https://127.0.0.1:8443/api/v1/collector",
        ),
        SeedTarget(
            "local",
            "postgresql://edr:x@127.0.0.1/customer",
            "http://edr:x@127.0.0.1/edr",
            "http://127.0.0.1:8080",
            "https://127.0.0.1:8443/api/v1/collector",
        ),
    ],
)
def test_destructive_seed_rejects_non_local_or_unknown_targets(target: SeedTarget) -> None:
    with pytest.raises(RuntimeError):
        assert_safe_reset_target(target)


def test_local_target_is_allowed() -> None:
    assert_safe_reset_target(
        SeedTarget(
            "local",
            "postgresql://edr:x@127.0.0.1:55432/edr",
            "http://edr:x@localhost:58123/edr",
            "http://127.0.0.1:8080",
            "https://127.0.0.1:8443/api/v1/collector",
        )
    )


def test_reset_function_rejects_missing_confirmation_before_connecting() -> None:
    target = SeedTarget(
        "local",
        "postgresql://edr:x@127.0.0.1:55432/edr",
        "http://edr:x@localhost:58123/edr",
        "http://127.0.0.1:8080",
        "https://127.0.0.1:8443/api/v1/collector",
    )

    with pytest.raises(RuntimeError, match="explicit --confirm-reset"):
        _reset_databases(target)


def test_clickhouse_down_continues_after_confirmed_unknown_table(tmp_path: Path) -> None:
    migration = tmp_path / "0002_test.down.sql"
    migration.write_text(
        "ALTER TABLE missing DROP INDEX IF EXISTS idx;\n"
        "DROP TABLE IF EXISTS remaining;\n",
        encoding="utf-8",
    )
    client = Mock()
    client.command.side_effect = [
        ClickHouseError("Code: 60. DB::Exception: missing. (UNKNOWN_TABLE)"),
        None,
    ]

    _apply_clickhouse_down_file(client, migration)

    assert [call.args[0] for call in client.command.call_args_list] == [
        "ALTER TABLE missing DROP INDEX IF EXISTS idx",
        "DROP TABLE IF EXISTS remaining",
    ]


@pytest.mark.parametrize(
    "message",
    [
        "Code: 60. DB::Exception: missing.",
        "Code: 62. DB::Exception: syntax error. (UNKNOWN_TABLE)",
        "DB::Exception: missing. (UNKNOWN_TABLE)",
    ],
)
def test_clickhouse_down_does_not_hide_unconfirmed_errors(tmp_path: Path, message: str) -> None:
    migration = tmp_path / "0002_test.down.sql"
    migration.write_text("ALTER TABLE missing DROP INDEX idx;\n", encoding="utf-8")
    client = Mock()
    client.command.side_effect = ClickHouseError(message)

    with pytest.raises(ClickHouseError, match="DB::Exception"):
        _apply_clickhouse_down_file(client, migration)


def test_reset_runs_all_clickhouse_down_files_in_reverse_then_all_up_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = SeedTarget(
        "local",
        "postgresql://edr:x@127.0.0.1:55432/edr",
        "http://edr:x@localhost:58123/edr",
        "http://127.0.0.1:8080",
        "https://127.0.0.1:8443/api/v1/collector",
    )
    connection_context = MagicMock()
    clickhouse = Mock()
    apply_down = Mock()
    apply_up = Mock()
    monkeypatch.setattr("tools.seed_presentation_demo.psycopg.connect", lambda _dsn: connection_context)
    monkeypatch.setattr("tools.seed_presentation_demo.apply_postgres_migrations", Mock())
    monkeypatch.setattr("tools.seed_presentation_demo.record_applied_postgres_migrations", Mock())
    monkeypatch.setattr("tools.seed_presentation_demo.clickhouse_connect.get_client", lambda **_kwargs: clickhouse)
    monkeypatch.setattr("tools.seed_presentation_demo._apply_clickhouse_down_file", apply_down)
    monkeypatch.setattr("tools.seed_presentation_demo.apply_clickhouse_file", apply_up)

    _reset_databases(target, confirm_reset=True)

    migration_root = Path(__file__).parents[1] / "migrations" / "clickhouse"
    assert [call.args[1].name for call in apply_down.call_args_list] == [
        path.name for path in sorted(migration_root.glob("*.down.sql"), reverse=True)
    ]
    assert [call.args[1].name for call in apply_up.call_args_list] == [
        path.name for path in sorted(migration_root.glob("*.up.sql"))
    ]
    clickhouse.close.assert_called_once_with()


def test_main_sanitizes_clickhouse_failure_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = SeedTarget(
        "local",
        "postgresql://edr:postgres-secret@127.0.0.1:55432/edr",
        "http://edr:clickhouse-secret@localhost:58123/edr",
        "http://127.0.0.1:8080",
        "https://127.0.0.1:8443/api/v1/collector",
    )
    monkeypatch.setattr("tools.seed_presentation_demo.seed_target", lambda: target)
    monkeypatch.setattr(
        "tools.seed_presentation_demo._reset_databases",
        Mock(side_effect=ClickHouseError("Code: 62. clickhouse-secret (SYNTAX_ERROR)")),
    )

    assert (
        main(
            [
                "--profile",
                "dns-correctness",
                "--confirm-reset",
                "--output-manifest",
                str(tmp_path / "manifest.json"),
            ]
        )
        == 2
    )

    stderr = capsys.readouterr().err
    assert stderr == "presentation demo seed failed: ClickHouse operation failed\n"
    assert "clickhouse-secret" not in stderr
    assert "Traceback" not in stderr


def _production_target() -> SeedTarget:
    return SeedTarget(
        "production",
        "postgresql://edr:postgres-secret@postgres:5432/edr",
        "http://edr:clickhouse-secret@clickhouse:8123/edr",
        "https://tukproject.dev",
        "https://api.tukproject.dev/api/v1/collector",
        production_demo_reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
        demo_reset_target_id="mentor-demo-team-c-20260723",
        kafka_bootstrap_servers="kafka:29092",
        kafka_raw_topic="telemetry.raw",
        kafka_validated_topic="telemetry.validated",
        event_storage_consumer_group="edr-event-storage-v1",
        detection_consumer_group="edr-detection-v1",
        s3_bucket="team-c-mentor-demo-bucket",
    )


def test_production_demo_dry_run_prints_sanitized_target_and_seeds_no_accounts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = _production_target()
    monkeypatch.setattr("tools.seed_presentation_demo.seed_target", lambda: target)

    assert (
        main(
            [
                "--profile",
                "presentation",
                "--seed",
                "20260721",
                "--anchor",
                "2026-07-21T12:20:00Z",
                "--production-demo-reset",
                "--output-manifest",
                "/tmp/edr-c-demo/presentation-manifest.json",
                "--dry-run",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "reset mode:       production-demo-full-reset" in output
    assert "accounts seeded:  no" in output
    assert production_demo_fingerprint(target) in output
    assert "postgres-secret" not in output
    assert "clickhouse-secret" not in output


def test_production_demo_rejects_missing_confirmation_before_preflight_or_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _production_target()
    preflight = Mock()
    reset = Mock()
    monkeypatch.setattr("tools.seed_presentation_demo.seed_target", lambda: target)
    monkeypatch.setattr("tools.seed_presentation_demo._preflight_manifest_output", preflight)
    monkeypatch.setattr("tools.seed_presentation_demo._reset_databases", reset)

    assert (
        main(
            [
                "--production-demo-reset",
                "--output-manifest",
                "/tmp/edr-c-demo/presentation-manifest.json",
                "--confirm-reset",
            ]
        )
        == 2
    )

    preflight.assert_not_called()
    reset.assert_not_called()


def test_production_demo_wires_full_confirmation_and_skips_default_accounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _production_target()
    fingerprint = production_demo_fingerprint(target)
    preflight = Mock()
    reset = Mock()
    direct_seed = Mock(
        return_value=(
            {"SOYEON-WIN": 3},
            {
                "chainIncidentId": 1,
                "powershellAlertIds": [1, 2],
                "egressAlertId": 3,
                "eventIds": [],
            },
        )
    )
    write_manifest = Mock()
    manifest = Mock(return_value={"accountsSeeded": False})
    output_path = Path("/tmp/edr-c-demo/presentation-manifest.json").resolve()
    monkeypatch.setattr("tools.seed_presentation_demo.seed_target", lambda: target)
    monkeypatch.setattr("tools.seed_presentation_demo._preflight_manifest_output", preflight)
    monkeypatch.setattr("tools.seed_presentation_demo._reset_databases", reset)
    monkeypatch.setattr("tools.seed_presentation_demo._direct_seed", direct_seed)
    monkeypatch.setattr("tools.seed_presentation_demo._manifest", manifest)
    monkeypatch.setattr("tools.seed_presentation_demo._write_manifest", write_manifest)

    assert (
        main(
            [
                "--production-demo-reset",
                "--output-manifest",
                str(output_path),
                "--confirm-reset",
                "--confirm-production-demo-reset",
                PRODUCTION_DEMO_RESET_CONFIRMATION,
                "--confirm-runtime-stopped",
                PRODUCTION_RUNTIME_STOPPED_CONFIRMATION,
                "--target-fingerprint",
                fingerprint,
            ]
        )
        == 0
    )

    preflight.assert_called_once_with(output_path)
    reset.assert_called_once_with(
        target,
        confirm_reset=True,
        production_demo_reset=True,
        production_confirmation=PRODUCTION_DEMO_RESET_CONFIRMATION,
        runtime_stopped_confirmation=PRODUCTION_RUNTIME_STOPPED_CONFIRMATION,
        target_fingerprint=fingerprint,
    )
    direct_seed.assert_called_once()
    assert direct_seed.call_args.kwargs["seed_default_users"] is False
    assert manifest.call_args.kwargs["accounts_seeded"] is False
    assert manifest.call_args.kwargs["target_fingerprint"] == fingerprint
    write_manifest.assert_called_once_with(output_path, {"accountsSeeded": False})


@pytest.mark.parametrize(
    "arguments",
    [
        ["--production-demo-reset", "--profile", "dns-correctness"],
        ["--production-demo-reset", "--emit-through-collector"],
        ["--production-demo-reset", "--output-manifest", "relative.json"],
    ],
)
def test_production_demo_rejects_unsupported_or_unsafe_modes(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
) -> None:
    monkeypatch.setattr("tools.seed_presentation_demo.seed_target", _production_target)
    assert main([*arguments, "--dry-run"]) == 2


@pytest.mark.parametrize(
    "path",
    [
        Path("/tmp/edr-c-demo"),
        Path("/tmp/edr-c-demo-sibling/presentation-manifest.json"),
        Path("/tmp/presentation-manifest.json"),
    ],
)
def test_production_demo_manifest_must_be_below_allowed_root(path: Path) -> None:
    with pytest.raises(ValueError, match="below /tmp/edr-c-demo"):
        _manifest_output_path(path, "presentation", production_demo_reset=True)


def test_production_demo_manifest_rejects_existing_directory() -> None:
    allowed_root = Path("/tmp/edr-c-demo")
    allowed_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pytest-manifest-dir-", dir=allowed_root) as directory:
        with pytest.raises(ValueError, match="regular file"):
            _manifest_output_path(
                Path(directory),
                "presentation",
                production_demo_reset=True,
            )


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="requires a POSIX FIFO")
def test_production_demo_manifest_rejects_non_regular_destination() -> None:
    allowed_root = Path("/tmp/edr-c-demo")
    allowed_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pytest-manifest-fifo-", dir=allowed_root) as directory:
        fifo = Path(directory) / "presentation-manifest.json"
        os.mkfifo(fifo)

        with pytest.raises(ValueError, match="regular file"):
            _manifest_output_path(fifo, "presentation", production_demo_reset=True)


def test_manifest_preflight_creates_parent_without_creating_or_leaking_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "missing-parent" / "presentation-manifest.json"

    _preflight_manifest_output(target)

    assert target.parent.is_dir()
    assert not target.exists()
    assert list(target.parent.iterdir()) == []


def test_manifest_preflight_preserves_existing_regular_file(tmp_path: Path) -> None:
    target = tmp_path / "presentation-manifest.json"
    target.write_text("keep-existing-manifest\n", encoding="utf-8")
    mode_before = target.stat().st_mode

    _preflight_manifest_output(target)

    assert target.read_text(encoding="utf-8") == "keep-existing-manifest\n"
    assert target.stat().st_mode == mode_before
    assert sorted(path.name for path in tmp_path.iterdir()) == [target.name]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="requires a POSIX FIFO")
def test_manifest_preflight_rejects_directory_and_non_regular_targets(tmp_path: Path) -> None:
    directory = tmp_path / "directory-target"
    directory.mkdir()
    fifo = tmp_path / "fifo-target"
    os.mkfifo(fifo)

    for target in (directory, fifo):
        with pytest.raises(ValueError, match="regular file"):
            _preflight_manifest_output(target)


def test_production_demo_preflight_failure_happens_before_database_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _production_target()
    fingerprint = production_demo_fingerprint(target)
    preflight = Mock(side_effect=OSError("manifest destination is not writable"))
    reset = Mock()
    monkeypatch.setattr("tools.seed_presentation_demo.seed_target", lambda: target)
    monkeypatch.setattr("tools.seed_presentation_demo._preflight_manifest_output", preflight)
    monkeypatch.setattr("tools.seed_presentation_demo._reset_databases", reset)

    assert (
        main(
            [
                "--production-demo-reset",
                "--output-manifest",
                "/tmp/edr-c-demo/presentation-manifest.json",
                "--confirm-reset",
                "--confirm-production-demo-reset",
                PRODUCTION_DEMO_RESET_CONFIRMATION,
                "--confirm-runtime-stopped",
                PRODUCTION_RUNTIME_STOPPED_CONFIRMATION,
                "--target-fingerprint",
                fingerprint,
            ]
        )
        == 2
    )

    preflight.assert_called_once()
    reset.assert_not_called()
