import json
from pathlib import Path

from backend.contracts.api_manifest import PRODUCT_API_CONTRACTS
from backend.main import create_app
from tools.export_openapi import render_openapi

ROOT = Path(__file__).parents[1]
TAGS = {"Auth", "Endpoints", "Events", "Archives", "Alerts", "Incidents", "Dashboard", "Operations", "Collector"}
EXPECTED_RESPONSES = {
    "authLogin": {"200", "400", "401", "403", "503"},
    "endpointsList": {"200", "400", "401", "503"},
    "endpointsGet": {"200", "400", "401", "404", "503"},
    "endpointsGetProcessTree": {"200", "400", "401", "503"},
    "eventsList": {"200", "400", "401", "409", "503"},
    "eventsGet": {"200", "400", "401", "404", "409", "503"},
    "failuresList": {"200", "400", "401", "503"},
    "archiveRestoresStart": {"200", "202", "400", "401", "403", "503"},
    "archiveRestoresList": {"200", "400", "401", "503"},
    "alertsList": {"200", "400", "401", "503"},
    "alertsGet": {"200", "400", "401", "404", "503"},
    "alertsUpdateStatus": {"200", "400", "401", "403", "404", "503"},
    "incidentsList": {"200", "400", "401", "503"},
    "incidentsGet": {"200", "400", "401", "404", "503"},
    "incidentsGetTimeline": {"200", "400", "401", "404", "503"},
    "dashboardGetSummary": {"200", "400", "401", "503"},
    "dashboardLayoutsGet": {"200", "401", "404", "503"},
    "dashboardLayoutsPut": {"200", "400", "401", "404", "409", "503"},
    "dashboardLayoutsDelete": {"200", "401", "404", "503"},
    "dashboardGetEndpointSummary": {"200", "400", "401", "503"},
    "dashboardGetIngestSummary": {"200", "400", "401", "503"},
    "dashboardGetTopology": {"200", "400", "401", "503"},
    "operationsGetHealth": {"200", "401"},
    "collectorRegisterAgent": {"200", "201", "400", "401", "403", "409", "503"},
    "collectorHeartbeatAgent": {"200", "400", "401", "403", "503"},
    "collectorIngestTelemetryBatch": {"200", "400", "401", "403", "413", "503"},
}


def operations(schema: dict) -> list[tuple[str, str, dict]]:
    return [
        (path, method, operation)
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
    ]


def test_openapi_has_exact_product_operations_tags_and_unique_ids() -> None:
    schema = create_app().openapi()
    items = operations(schema)
    expected = {(contract.method.lower(), "/api/v1" + contract.path) for contract in PRODUCT_API_CONTRACTS}
    assert {(method, path) for path, method, _operation in items} == expected
    assert len(items) == 26
    operation_ids = [operation["operationId"] for _path, _method, operation in items]
    assert len(operation_ids) == len(set(operation_ids)) == 26
    assert set(operation_ids) == EXPECTED_RESPONSES.keys()
    assert {tag["name"] for tag in schema["tags"]} == TAGS
    assert all(len(operation["tags"]) == 1 and operation["tags"][0] in TAGS for _, _, operation in items)


def test_openapi_security_headers_and_responses_match_runtime_contract() -> None:
    schema = create_app().openapi()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["BearerJWT"]["type"] == "http"
    assert schemes["BearerJWT"]["scheme"] == "bearer"
    assert schemes["mutualTLS"]["type"] == "mutualTLS"
    for path, _method, operation in operations(schema):
        if operation["operationId"] == "authLogin":
            assert "security" not in operation
        elif path.startswith("/api/v1/collector/"):
            assert operation["security"] == [{"mutualTLS": []}]
        else:
            assert operation["security"] == [{"BearerJWT": []}]
        assert set(operation["responses"]) == EXPECTED_RESPONSES[operation["operationId"]]
        assert "422" not in operation["responses"]
        parameter_names = {parameter["name"].lower() for parameter in operation.get("parameters", [])}
        assert not any(name.startswith("x-edr-") for name in parameter_names)


def test_openapi_request_and_envelope_components_are_codegen_ready() -> None:
    schema = create_app().openapi()
    schemas = schema["components"]["schemas"]
    assert "ErrorEnvelope" in schemas
    assert any(name.startswith("SuccessEnvelope_") for name in schemas)
    assert any(name.startswith("PagedData_") for name in schemas)
    assert schemas["TelemetryBatchRequest"]["required"] == ["schemaVersion", "batchId", "agentId", "sentAt", "events"]
    telemetry = schema["paths"]["/api/v1/collector/telemetry/batches"]["post"]
    assert telemetry["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TelemetryBatchRequest"
    }
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas
    assert schemas["DnsQueryPayload"]["required"] == ["query", "recordType"]
    assert "default" not in schemas["DnsQueryPayload"]["properties"]["responseCode"]


def test_checked_in_openapi_artifact_matches_app() -> None:
    artifact = ROOT / "openapi/openapi.json"
    assert artifact.read_text(encoding="utf-8") == render_openapi()
    assert json.loads(render_openapi()) == create_app().openapi()
