from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def _compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def test_local_compose_contains_the_complete_development_stack() -> None:
    services = _compose()["services"]

    assert set(services) == {
        "postgres",
        "clickhouse",
        "kafka",
        "minio",
        "cert-init",
        "app-init",
        "backend",
        "event-storage-worker",
        "detection-worker",
        "frontend",
        "nginx",
    }
    assert "ports" not in services["backend"]
    assert services["backend"]["depends_on"]["app-init"]["condition"] == "service_completed_successfully"
    assert services["nginx"]["depends_on"]["frontend"]["condition"] == "service_healthy"
    assert services["frontend"]["environment"]["EDR_BACKEND_PROXY_TARGET"] == "http://backend:8000"


def test_app_containers_use_compose_internal_service_addresses() -> None:
    environment = _compose()["x-app-environment"]

    assert "@postgres:5432/" in environment["EDR_POSTGRES_DSN"]
    assert "@clickhouse:8123/" in environment["EDR_CLICKHOUSE_DSN"]
    assert environment["EDR_KAFKA_BOOTSTRAP_SERVERS"] == "kafka:29092"
    assert environment["EDR_S3_ENDPOINT_URL"] == "http://minio:9000"


def test_nginx_has_separate_public_and_mtls_collectors() -> None:
    nginx = (ROOT / "deploy/nginx/nginx.dev.conf").read_text(encoding="utf-8")

    assert "listen 8080;" in nginx
    assert "listen 8443 ssl;" in nginx
    assert "ssl_verify_client on;" in nginx
    assert "X-EDR-Client-Certificate $ssl_client_escaped_cert" in nginx
    assert "location ^~ /api/v1/collector/" in nginx


def test_nginx_rate_limits_dashboard_login_with_a_contract_error() -> None:
    nginx = (ROOT / "deploy/nginx/nginx.dev.conf").read_text(encoding="utf-8")

    assert "limit_req_zone $binary_remote_addr zone=dashboard_login:10m rate=10r/m;" in nginx
    assert "location = /api/v1/auth/login" in nginx
    assert "limit_req_status 429;" in nginx
    assert '"code":"RATE_LIMITED"' in nginx
