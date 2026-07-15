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


def test_portainer_server_is_pinned_and_exposes_only_loopback_https() -> None:
    server = _load("compose.portainer-server.yaml")
    portainer = server["services"]["portainer"]

    assert set(server["services"]) == {"portainer"}
    assert portainer["image"] == "portainer/portainer-ce:2.39.5-alpine"
    assert portainer["ports"] == ["127.0.0.1:9443:9443"]
    assert portainer["restart"] == "unless-stopped"
    assert portainer["volumes"] == [
        "/var/run/docker.sock:/var/run/docker.sock",
        "portainer-data:/data",
    ]
    assert server["volumes"]["portainer-data"] == {
        "external": True,
        "name": "portainer_data",
    }
    assert server["networks"]["portainer-network"] == {"name": "portainer-network"}


def test_portainer_agent_is_pinned_and_preserves_required_host_mounts() -> None:
    agent_compose = _load("compose.portainer-agent.yaml")
    agent = agent_compose["services"]["portainer-agent"]

    assert agent_compose["name"] == "portainer"
    assert set(agent_compose["services"]) == {"portainer-agent"}
    assert agent["image"] == "portainer/agent:2.39.5-alpine"
    assert agent["container_name"] == "portainer-agent"
    assert agent["ports"] == ["9001:9001"]
    assert agent["restart"] == "unless-stopped"
    assert agent["volumes"] == [
        "/var/run/docker.sock:/var/run/docker.sock",
        "/var/lib/docker/volumes:/var/lib/docker/volumes",
        "/:/host",
    ]
    assert agent_compose["networks"]["portainer-network"] == {
        "external": True,
        "name": "portainer-network",
    }


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


def test_observability_stack_runs_pinned_alloy_without_public_ports() -> None:
    observability = _load("compose.observability.yaml")
    alloy = observability["services"]["alloy"]

    assert set(observability["services"]) == {"alloy"}
    assert alloy["image"] == "grafana/alloy:v1.17.0"
    assert "ports" not in alloy
    assert alloy["restart"] == "unless-stopped"
    assert observability["networks"]["data"] == {"external": True, "name": "edr-c-data"}
    assert "configs" not in observability
    assert "configs" not in alloy

    bind_sources = {
        volume["source"]
        for volume in alloy["volumes"]
        if isinstance(volume, dict) and volume["type"] == "bind"
    }
    assert bind_sources == {"/", "/proc", "/run/udev/data", "/sys", "/var/run/docker.sock"}

    udev_mount = next(
        volume
        for volume in alloy["volumes"]
        if isinstance(volume, dict) and volume["source"] == "/run/udev/data"
    )
    assert udev_mount["target"] == "/run/udev/data"
    assert udev_mount["read_only"] is True
    assert udev_mount["bind"] == {"create_host_path": False}
    assert "$$ALLOY_CONFIG" in alloy["command"][0]


def test_observability_stack_keeps_cloud_credentials_out_of_git() -> None:
    observability = _load("compose.observability.yaml")
    environment = observability["services"]["alloy"]["environment"]
    alloy_config = environment["ALLOY_CONFIG"]

    expected = {
        "GRAFANA_CLOUD_METRICS_URL",
        "GRAFANA_CLOUD_METRICS_USER",
        "GRAFANA_CLOUD_LOGS_URL",
        "GRAFANA_CLOUD_LOGS_USER",
        "GRAFANA_CLOUD_TOKEN",
    }
    assert set(environment) == expected | {"ALLOY_CONFIG"}
    assert all("is required" in environment[name] for name in expected)
    assert all(f'sys.env("{name}")' in alloy_config for name in expected)
    assert "grafana.net" not in alloy_config
    assert alloy_config == observability["x-alloy-config"]


def test_alloy_collects_only_the_intended_production_signals() -> None:
    observability = _load("compose.observability.yaml")
    alloy = observability["services"]["alloy"]["environment"]["ALLOY_CONFIG"]

    assert 'prometheus.exporter.unix "host"' in alloy
    assert 'prometheus.exporter.cadvisor "docker"' in alloy
    assert 'prometheus.exporter.kafka "kafka"' in alloy
    assert 'prometheus.exporter.blackbox "backend"' in alloy
    assert "http://backend:8000/health/ready" in alloy
    assert 'loki.source.docker "local"' in alloy
    assert 'regex         = "edr-c-(infra|service|observability)"' in alloy
    assert "targets = discovery.docker.local.targets" in alloy
    assert "targets = discovery.relabel.docker_logs.output" in alloy
    assert "relabel_rules" not in alloy
    assert "GRAFANA_CLOUD_TOKEN=" not in alloy


def test_portainer_environment_examples_cover_required_variables_without_secrets() -> None:
    expected = {
        "env.infra.example": {
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "CLICKHOUSE_USER",
            "CLICKHOUSE_PASSWORD",
            "POSTGRES_VOLUME_NAME",
            "CLICKHOUSE_VOLUME_NAME",
            "KAFKA_VOLUME_NAME",
        },
        "env.service.example": {
            "EDR_IMAGE_TAG",
            "EDR_JWT_SECRET",
            "EDR_POSTGRES_DSN",
            "EDR_CLICKHOUSE_DSN",
            "EDR_AWS_REGION",
            "EDR_S3_BUCKET",
        },
        "env.observability.example": {
            "GRAFANA_CLOUD_METRICS_URL",
            "GRAFANA_CLOUD_METRICS_USER",
            "GRAFANA_CLOUD_LOGS_URL",
            "GRAFANA_CLOUD_LOGS_USER",
            "GRAFANA_CLOUD_TOKEN",
        },
    }

    for filename, required_names in expected.items():
        lines = (PORTAINER / filename).read_text(encoding="utf-8").splitlines()
        values = dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))

        assert required_names <= values.keys()
        assert all(value for value in values.values())
        assert all(
            "<" in value and ">" in value
            for name, value in values.items()
            if name.endswith(("PASSWORD", "SECRET", "TOKEN"))
        )


def test_production_verifier_checks_health_and_current_api_contracts() -> None:
    verifier = (ROOT / "tools/verify_production_deployment.ps1").read_text(encoding="utf-8")

    assert '"/nginx-health"' in verifier
    assert '"/health/ready"' in verifier
    assert '"/openapi.json"' in verifier
    assert '"/api/v1/users/me/locale"' in verifier
    assert '"/api/v1/dashboard/layouts/{dashboardKey}"' in verifier
    assert '"/api/v1/endpoints/{endpointId}/process-tree"' in verifier
    assert "[string]$SshHost" in verifier
    assert "ssh $SshHost curl" in verifier
