import json
from collections import Counter
from datetime import UTC, datetime, timedelta

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

    assert plan.counts == {"endpoints": 5, "events": 5_600, "alerts": 3, "incidents": 2}
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
