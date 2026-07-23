import json

import pytest

from tools.seed_safety import (
    PRODUCTION_DEMO_RESET_CONFIRMATION,
    PRODUCTION_RUNTIME_STOPPED_CONFIRMATION,
    assert_production_demo_reset_authorized,
    assert_safe_reset_targets,
    parse_allowed_qa_hosts,
    production_demo_target_descriptor,
    production_demo_target_fingerprint,
    require_reset_confirmation,
)


def test_local_demo_targets_are_allowed() -> None:
    assert_safe_reset_targets(
        environment="local",
        targets=(
            ("PostgreSQL", "postgresql://edr:x@127.0.0.1:55432/edr"),
            ("ClickHouse", "http://edr:x@clickhouse:8123/edr_qa"),
        ),
    )


@pytest.mark.parametrize("environment", ["production", "staging", ""])
def test_destructive_seed_rejects_non_demo_environments(environment: str) -> None:
    with pytest.raises(RuntimeError, match="EDR_ENV"):
        assert_safe_reset_targets(
            environment=environment,
            targets=(("PostgreSQL", "postgresql://edr:x@127.0.0.1/edr"),),
        )


def test_remote_qa_host_requires_an_exact_allowlist_entry() -> None:
    target = (("PostgreSQL", "postgresql://edr:x@qa-db.example.internal/edr_qa"),)

    with pytest.raises(RuntimeError, match="not an allowlisted"):
        assert_safe_reset_targets(environment="qa", targets=target)

    assert_safe_reset_targets(
        environment="qa",
        targets=target,
        allowed_qa_hosts=parse_allowed_qa_hosts("qa-db.example.internal"),
    )


def test_hostname_substrings_and_unknown_databases_do_not_bypass_policy() -> None:
    with pytest.raises(RuntimeError, match="not an allowlisted"):
        assert_safe_reset_targets(
            environment="qa",
            targets=(("PostgreSQL", "postgresql://edr:x@production-qa-lookalike.example/edr"),),
        )
    with pytest.raises(RuntimeError, match="database is not an allowlisted"):
        assert_safe_reset_targets(
            environment="local",
            targets=(("PostgreSQL", "postgresql://edr:x@localhost/customer"),),
        )


def test_reset_confirmation_is_required() -> None:
    with pytest.raises(RuntimeError, match="explicit --confirm-reset"):
        require_reset_confirmation(False)

    require_reset_confirmation(True)


def test_qa_host_allowlist_rejects_wildcards() -> None:
    with pytest.raises(ValueError, match="wildcards"):
        parse_allowed_qa_hosts("*.qa.example.internal")


def _production_targets(
    postgres_password: str = "postgres-secret",
    clickhouse_password: str = "clickhouse-secret",
) -> tuple[tuple[str, str], tuple[str, str]]:
    return (
        ("PostgreSQL", f"postgresql://edr:{postgres_password}@postgres:5432/edr"),
        ("ClickHouse", f"http://edr:{clickhouse_password}@clickhouse:8123/edr"),
    )


def _production_runtime_context() -> dict[str, str]:
    return {
        "kafkaBootstrapServers": "kafka:29092",
        "kafkaRawTopic": "telemetry.raw",
        "kafkaValidatedTopic": "telemetry.validated",
        "eventStorageConsumerGroup": "edr-event-storage-v1",
        "detectionConsumerGroup": "edr-detection-v1",
        "s3Bucket": "team-c-mentor-demo-bucket",
    }


def test_production_demo_fingerprint_is_sanitized_and_ignores_password_changes() -> None:
    descriptor = production_demo_target_descriptor(
        environment="production",
        targets=_production_targets(),
        reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
        target_id="mentor-demo-team-c-20260723",
        runtime_context=_production_runtime_context(),
    )
    first = production_demo_target_fingerprint(
        environment="production",
        targets=_production_targets(),
        reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
        target_id="mentor-demo-team-c-20260723",
        runtime_context=_production_runtime_context(),
    )
    second = production_demo_target_fingerprint(
        environment="production",
        targets=_production_targets("rotated-postgres", "rotated-clickhouse"),
        reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
        target_id="mentor-demo-team-c-20260723",
        runtime_context=_production_runtime_context(),
    )

    assert first == second
    assert len(first) == 64
    serialized = json.dumps(descriptor, sort_keys=True)
    assert "postgres-secret" not in serialized
    assert "clickhouse-secret" not in serialized
    assert "password" not in serialized.lower()
    assert descriptor["purpose"] == "mentor-demo-full-reset"


@pytest.mark.parametrize("reset_mode", ["", "FULL_RESET", "full_reset_dedicated_mentor_demo"])
def test_production_demo_requires_exact_environment_reset_opt_in(reset_mode: str) -> None:
    with pytest.raises(RuntimeError, match="environment opt-in"):
        production_demo_target_fingerprint(
            environment="production",
            targets=_production_targets(),
            reset_mode=reset_mode,
            target_id="mentor-demo-team-c-20260723",
            runtime_context=_production_runtime_context(),
        )


@pytest.mark.parametrize(
    "target_id",
    [
        "",
        "production",
        "mentor-demo",
        "mentor-demo-short",
        "mentor-demo-team/c-20260723",
    ],
)
def test_production_demo_requires_unique_target_identifier_format(target_id: str) -> None:
    with pytest.raises(RuntimeError, match=r"mentor-demo-\*"):
        production_demo_target_fingerprint(
            environment="production",
            targets=_production_targets(),
            reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
            target_id=target_id,
            runtime_context=_production_runtime_context(),
        )


def test_production_demo_fingerprint_changes_with_target_id_and_runtime_context() -> None:
    baseline = production_demo_target_fingerprint(
        environment="production",
        targets=_production_targets(),
        reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
        target_id="mentor-demo-team-c-20260723",
        runtime_context=_production_runtime_context(),
    )
    different_target = production_demo_target_fingerprint(
        environment="production",
        targets=_production_targets(),
        reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
        target_id="mentor-demo-team-c-20260724",
        runtime_context=_production_runtime_context(),
    )
    changed_runtime = _production_runtime_context()
    changed_runtime["kafkaRawTopic"] = "telemetry.raw.mentor-demo"
    different_runtime = production_demo_target_fingerprint(
        environment="production",
        targets=_production_targets(),
        reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
        target_id="mentor-demo-team-c-20260723",
        runtime_context=changed_runtime,
    )

    assert len({baseline, different_target, different_runtime}) == 3


@pytest.mark.parametrize(
    "runtime_context",
    [
        {
            key: value
            for key, value in _production_runtime_context().items()
            if key != "s3Bucket"
        },
        {**_production_runtime_context(), "unexpected": "value"},
        {**_production_runtime_context(), "s3Bucket": ""},
        {**_production_runtime_context(), "s3Bucket": "<unset>"},
    ],
)
def test_production_demo_requires_complete_concrete_runtime_context(
    runtime_context: dict[str, str],
) -> None:
    with pytest.raises(RuntimeError, match="runtime context"):
        production_demo_target_fingerprint(
            environment="production",
            targets=_production_targets(),
            reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
            target_id="mentor-demo-team-c-20260723",
            runtime_context=runtime_context,
        )


@pytest.mark.parametrize(
    ("targets", "message"),
    [
        (
            (
                ("PostgreSQL", "postgresql://edr:x@production.example:5432/edr"),
                ("ClickHouse", "http://edr:x@clickhouse:8123/edr"),
            ),
            "dedicated production demo target",
        ),
        (
            (
                ("PostgreSQL", "postgresql://edr:x@postgres:5432/customer"),
                ("ClickHouse", "http://edr:x@clickhouse:8123/edr"),
            ),
            "dedicated production demo target",
        ),
        (
            (
                ("PostgreSQL", "postgresql://edr@postgres:5432/edr"),
                ("ClickHouse", "http://edr:x@clickhouse:8123/edr"),
            ),
            "dedicated production demo target",
        ),
    ],
)
def test_production_demo_rejects_non_exact_targets(
    targets: tuple[tuple[str, str], tuple[str, str]],
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        production_demo_target_fingerprint(
            environment="production",
            targets=targets,
            reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
            target_id="mentor-demo-team-c-20260723",
            runtime_context=_production_runtime_context(),
        )


def test_production_demo_requires_all_confirmation_values() -> None:
    targets = _production_targets()
    fingerprint = production_demo_target_fingerprint(
        environment="production",
        targets=targets,
        reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
        target_id="mentor-demo-team-c-20260723",
        runtime_context=_production_runtime_context(),
    )

    with pytest.raises(RuntimeError, match="confirm-production-demo-reset"):
        assert_production_demo_reset_authorized(
            environment="production",
            targets=targets,
            reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
            target_id="mentor-demo-team-c-20260723",
            runtime_context=_production_runtime_context(),
            confirmation=None,
            runtime_stopped_confirmation=PRODUCTION_RUNTIME_STOPPED_CONFIRMATION,
            target_fingerprint=fingerprint,
        )
    with pytest.raises(RuntimeError, match="ingress and workers"):
        assert_production_demo_reset_authorized(
            environment="production",
            targets=targets,
            reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
            target_id="mentor-demo-team-c-20260723",
            runtime_context=_production_runtime_context(),
            confirmation=PRODUCTION_DEMO_RESET_CONFIRMATION,
            runtime_stopped_confirmation=None,
            target_fingerprint=fingerprint,
        )
    with pytest.raises(RuntimeError, match="fingerprint"):
        assert_production_demo_reset_authorized(
            environment="production",
            targets=targets,
            reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
            target_id="mentor-demo-team-c-20260723",
            runtime_context=_production_runtime_context(),
            confirmation=PRODUCTION_DEMO_RESET_CONFIRMATION,
            runtime_stopped_confirmation=PRODUCTION_RUNTIME_STOPPED_CONFIRMATION,
            target_fingerprint="0" * 64,
        )

    assert (
        assert_production_demo_reset_authorized(
            environment="production",
            targets=targets,
            reset_mode=PRODUCTION_DEMO_RESET_CONFIRMATION,
            target_id="mentor-demo-team-c-20260723",
            runtime_context=_production_runtime_context(),
            confirmation=PRODUCTION_DEMO_RESET_CONFIRMATION,
            runtime_stopped_confirmation=PRODUCTION_RUNTIME_STOPPED_CONFIRMATION,
            target_fingerprint=fingerprint,
        )
        == fingerprint
    )
