from fastapi.testclient import TestClient

from backend.contracts.api_manifest import PRODUCT_API_CONTRACTS
from backend.main import create_app


class ReadyRuntime:
    def check_ready(self) -> None:
        return None


def test_operational_health_routes_only() -> None:
    client = TestClient(create_app(ReadyRuntime()))
    assert client.get("/health/live").json() == {"status": "live"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    openapi_paths = client.get("/openapi.json").json()["paths"]
    expected = {(contract.method.lower(), "/api/v1" + contract.path) for contract in PRODUCT_API_CONTRACTS}
    actual = {(method, path) for path, operations in openapi_paths.items() for method in operations}
    assert actual == expected
    assert len(actual) == 23

    register_responses = openapi_paths["/api/v1/collector/agents/register"]["post"]["responses"]
    restore_responses = openapi_paths["/api/v1/archives/restores"]["post"]["responses"]
    telemetry = openapi_paths["/api/v1/collector/telemetry/batches"]["post"]
    assert {"200", "201"} <= register_responses.keys()
    assert {"200", "202"} <= restore_responses.keys()
    telemetry_schema = telemetry["requestBody"]["content"]["application/json"]["schema"]
    assert telemetry_schema == {"$ref": "#/components/schemas/TelemetryBatchRequest"}
    assert not telemetry.get("parameters")


def test_readiness_fails_closed() -> None:
    class NotReadyRuntime:
        def check_ready(self) -> None:
            raise RuntimeError("dependency down")

    response = TestClient(create_app(NotReadyRuntime())).get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
