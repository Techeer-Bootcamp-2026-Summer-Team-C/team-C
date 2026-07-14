from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def _compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def _production_compose() -> dict:
    return yaml.safe_load((ROOT / "compose.prod.yaml").read_text(encoding="utf-8"))


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
    assert environment["EDR_AWS_REGION"] == "${EDR_AWS_REGION:-us-east-1}"
    assert environment["EDR_KAFKA_PARTITIONS_PER_TOPIC"] == "${EDR_KAFKA_PARTITIONS_PER_TOPIC:-2}"


def test_production_compose_contains_only_the_required_runtime_services() -> None:
    services = _production_compose()["services"]

    assert set(services) == {
        "postgres",
        "clickhouse",
        "kafka",
        "app-init",
        "backend",
        "event-storage-worker",
        "detection-worker",
        "nginx",
    }
    assert "minio" not in services
    assert "frontend" not in services
    assert "cert-init" not in services
    assert "ports" not in services["postgres"]
    assert "ports" not in services["clickhouse"]
    assert "ports" not in services["kafka"]
    assert "ports" not in services["backend"]
    assert services["nginx"]["ports"] == [
        "${NGINX_HTTP_HOST_PORT:-8080}:8080",
        "${NGINX_MTLS_HOST_PORT:-8443}:8443",
    ]


def test_production_apps_use_internal_data_services_and_iam_role_s3() -> None:
    environment = _production_compose()["x-app-environment"]

    assert environment["EDR_ENV"] == "production"
    assert "@postgres:5432/" in environment["EDR_POSTGRES_DSN"]
    assert "@clickhouse:8123/" in environment["EDR_CLICKHOUSE_DSN"]
    assert environment["EDR_KAFKA_BOOTSTRAP_SERVERS"] == "kafka:29092"
    assert environment["EDR_AWS_REGION"] == "${EDR_AWS_REGION:?EDR_AWS_REGION is required}"
    assert environment["EDR_S3_BUCKET"] == "${EDR_S3_BUCKET:?EDR_S3_BUCKET is required}"
    assert "EDR_S3_ENDPOINT_URL" not in environment
    assert "EDR_S3_ACCESS_KEY_ID" not in environment
    assert "EDR_S3_SECRET_ACCESS_KEY" not in environment


def test_production_init_is_safe_and_does_not_call_local_demo_or_s3() -> None:
    compose = _production_compose()
    services = compose["services"]
    source = (ROOT / "tools/prod_init.py").read_text(encoding="utf-8")

    assert services["app-init"]["command"] == ["python", "-m", "tools.prod_init"]
    assert set(services["app-init"]["depends_on"]) == {"postgres", "clickhouse", "kafka"}
    assert "local_demo" not in source
    assert "boto3" not in source
    assert "create_bucket" not in source
    assert "UserRepository" not in source


def test_production_workers_default_to_one_scalable_service_each() -> None:
    services = _production_compose()["services"]

    for worker_name in ("event-storage-worker", "detection-worker"):
        worker = services[worker_name]
        assert "container_name" not in worker
        assert "deploy" not in worker
    assert services["event-storage-worker"]["command"] == ["python", "-m", "tools.run_event_storage_worker"]
    assert services["detection-worker"]["command"] == ["python", "-m", "tools.run_detection_worker"]


def test_production_example_has_no_access_key_fields() -> None:
    example = (ROOT / ".env.production.example").read_text(encoding="utf-8")

    assert "EDR_AWS_REGION=" in example
    assert "EDR_S3_BUCKET=" in example
    assert "S3_ACCESS_KEY" not in example
    assert "S3_SECRET_ACCESS_KEY" not in example


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
