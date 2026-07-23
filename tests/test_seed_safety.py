import pytest

from tools.seed_safety import (
    assert_safe_reset_targets,
    parse_allowed_qa_hosts,
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
