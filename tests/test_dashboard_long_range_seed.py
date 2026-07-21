from datetime import UTC, datetime

import pytest

from tools.seed_dashboard_long_range import SeedConfig, build_endpoint_seeds, main


def test_default_long_range_seed_estimate() -> None:
    config = SeedConfig()

    config.validate()

    assert config.event_count == 14_000
    assert config.alert_count == 280
    assert config.incident_count == 40
    assert config.failure_count == 35
    assert config.hot_bucket_count == 160


def test_long_range_seed_requires_at_least_seven_days() -> None:
    with pytest.raises(ValueError, match="days must be between 7 and 31"):
        SeedConfig(days=6).validate()


def test_endpoint_seed_contains_all_operational_states() -> None:
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)

    endpoints = build_endpoint_seeds(SeedConfig(endpoint_count=20), now=now)

    assert len(endpoints) == 20
    assert {endpoint.status for endpoint in endpoints} == {"ONLINE", "OFFLINE", "RETIRED"}
    assert {endpoint.os_type for endpoint in endpoints} == {"WINDOWS", "MACOS"}
    assert all(endpoint.event_window_start < endpoint.event_window_end for endpoint in endpoints)


def test_dry_run_does_not_require_reset_confirmation(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--dry-run", "--days", "7", "--endpoints", "10", "--events-per-endpoint-day", "20"]) == 0

    output = capsys.readouterr().out
    assert "Events:           1,400" in output
    assert "Endpoints:        10" in output


def test_presentation_performance_shape_is_exactly_248000_events(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "--dry-run",
                "--days",
                "31",
                "--endpoints",
                "100",
                "--events-per-endpoint-day",
                "80",
                "--seed",
                "20260715",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Events:           248,000" in output
    assert "Endpoints:        100" in output
