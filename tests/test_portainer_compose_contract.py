from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
PORTAINER = ROOT / "deploy/portainer"


def _load(name: str) -> dict:
    return yaml.safe_load((PORTAINER / name).read_text(encoding="utf-8"))


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False


def test_portainer_stacks_split_infrastructure_from_services() -> None:
    infra = _load("compose.infra.yaml")
    service = _load("compose.service.yaml")

    assert set(infra["services"]) == {"postgres", "clickhouse", "kafka"}
    assert set(service["services"]) == {
        "app-init",
        "backend",
        "event-storage-worker",
        "detection-worker",
        "nginx",
    }
    assert "frontend" not in infra["services"] | service["services"]
    assert "minio" not in infra["services"] | service["services"]


def test_portainer_stacks_never_build_on_the_remote_environment() -> None:
    infra = _load("compose.infra.yaml")
    service = _load("compose.service.yaml")

    assert not _contains_key(infra, "build")
    assert not _contains_key(service, "build")
    assert "${EDR_IMAGE_TAG:?EDR_IMAGE_TAG is required}" in service["x-backend-image"]
    assert ":latest" not in (PORTAINER / "compose.service.yaml").read_text(encoding="utf-8")


def test_infrastructure_data_uses_stable_external_resources() -> None:
    infra = _load("compose.infra.yaml")

    assert infra["networks"]["data"] == {"external": True, "name": "edr-c-data"}
    assert infra["volumes"] == {
        "postgres-data": {
            "external": True,
            "name": "${POSTGRES_VOLUME_NAME:?POSTGRES_VOLUME_NAME is required}",
        },
        "clickhouse-data": {
            "external": True,
            "name": "${CLICKHOUSE_VOLUME_NAME:?CLICKHOUSE_VOLUME_NAME is required}",
        },
        "kafka-data": {
            "external": True,
            "name": "${KAFKA_VOLUME_NAME:?KAFKA_VOLUME_NAME is required}",
        },
    }
    for service_name in ("postgres", "clickhouse", "kafka"):
        assert "ports" not in infra["services"][service_name]


def test_service_stack_uses_the_shared_data_network_and_waits_for_init() -> None:
    service = _load("compose.service.yaml")
    services = service["services"]

    assert service["networks"]["data"] == {"external": True, "name": "edr-c-data"}
    assert "depends_on" not in services["app-init"]
    for name in ("backend", "event-storage-worker", "detection-worker"):
        assert services[name]["depends_on"]["app-init"]["condition"] == "service_completed_successfully"


def test_nginx_uses_a_fixed_existing_ec2_certificate_directory() -> None:
    nginx = _load("compose.service.yaml")["services"]["nginx"]
    mount = nginx["volumes"][0]

    assert mount == {
        "type": "bind",
        "source": "/etc/edr-c/tls",
        "target": "/etc/nginx/certs",
        "read_only": True,
        "bind": {"create_host_path": False},
    }


def test_production_images_are_built_for_ec2_and_tagged_with_the_commit() -> None:
    workflow = (ROOT / ".github/workflows/build-prod-images.yml").read_text(encoding="utf-8")
    nginx_dockerfile = (ROOT / "deploy/docker/nginx.Dockerfile").read_text(encoding="utf-8")

    assert "platforms: linux/amd64" in workflow
    assert "techeer-bootcamp-2026-summer-team-c" in workflow
    assert "${{ github.sha }}" in workflow
    assert "team-c-backend" in workflow
    assert "team-c-nginx" in workflow
    assert ":latest" not in workflow
    assert "COPY deploy/nginx/nginx.prod.conf /etc/nginx/nginx.conf" in nginx_dockerfile


def test_nginx_resolves_recreated_backend_containers_through_docker_dns() -> None:
    nginx = (ROOT / "deploy/nginx/nginx.prod.conf").read_text(encoding="utf-8")

    assert "resolver 127.0.0.11" in nginx
    assert "zone backend_upstream" in nginx
    assert "server backend:8000 resolve;" in nginx
