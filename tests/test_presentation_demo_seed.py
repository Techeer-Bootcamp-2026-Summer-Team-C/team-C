import json
from datetime import UTC, datetime

import pytest

from tools.seed_presentation_demo import (
    SeedTarget,
    assert_safe_reset_target,
    build_dns_correctness_plan,
    build_presentation_plan,
    main,
    parse_anchor,
)

ANCHOR = datetime(2026, 7, 21, 12, 20, tzinfo=UTC)


def test_presentation_profile_has_exact_counts_distribution_and_correlation() -> None:
    plan = build_presentation_plan(20_260_721, ANCHOR)

    assert plan.counts == {"endpoints": 3, "events": 64, "alerts": 3, "incidents": 2}
    assert {endpoint.hostname: endpoint.event_count for endpoint in plan.endpoints} == {
        "DEMO-STUDENT-WIN-07": 24,
        "DEMO-DEV-WIN-02": 24,
        "DEMO-FINANCE-MAC-02": 16,
    }
    powershell = [
        event
        for event in plan.events
        if event.event_type == "PROCESS_EXECUTION" and "-EncodedCommand" in str(event.payload.get("commandLine"))
    ]
    assert len(powershell) == 2
    assert {event.hostname for event in powershell} == {"DEMO-STUDENT-WIN-07"}
    assert abs((powershell[1].occurred_at - powershell[0].occurred_at).total_seconds()) < 1_800


def test_profile_generation_is_deterministic_for_seed_and_anchor() -> None:
    first = build_presentation_plan(7, ANCHOR)
    second = build_presentation_plan(7, ANCHOR)

    assert first.events == second.events
    assert len({event.event_id for event in first.events}) == 64
    assert len({event.batch_id for event in first.events}) == 64


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
    assert "Endpoints:        3" in output
    assert "Events:           64" in output
    assert "Alerts:           3" in output
    assert "Incidents:        2" in output
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
