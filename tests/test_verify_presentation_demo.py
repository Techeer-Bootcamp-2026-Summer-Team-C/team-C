import httpx

from tools.verify_presentation_demo import _verify_presentation


def test_verify_presentation_requires_one_three_alert_chain_incident() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        query = request.url.query.decode()
        if path == "/api/v1/dashboard/summary":
            events = 2_800 if "LATEST_7D" in query else 400
            return httpx.Response(
                200,
                json={
                    "data": {
                        "endpoints": {"totalCount": 5},
                        "events": {"totalCount": events},
                        "alerts": {"totalCount": 3},
                        "incidents": {"openCount": 1},
                    }
                },
            )
        if path == "/api/v1/incidents/42":
            return httpx.Response(
                200,
                json={"data": {"correlationKey": "powershell-tls-egress-chain", "alertCount": 3}},
            )
        if path == "/api/v1/incidents/42/timeline":
            return httpx.Response(200, json={"data": {"items": [{"id": index} for index in range(6)]}})
        if path == "/api/v1/endpoints/7":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "hostname": "SOYEON-WIN",
                        "risk": {"activeAlertCount": 3, "openIncidentCount": 1},
                    }
                },
            )
        if path == "/api/v1/events":
            return httpx.Response(200, json={"data": {"total": 85}})
        raise AssertionError(f"unexpected request: {request.url}")

    manifest = {
        "counts": {"endpoints": 5, "events": 5_600, "alerts": 3, "incidents": 1},
        "rangeCounts": {"latest24h": 400, "latest7d": 2_800},
        "ids": {
            "chainIncidentId": 42,
            "presentationEndpointId": 7,
            "endpointIdsByHostname": {
                "GEONHA-MACMINI": 1,
                "GEONHA-WIN": 2,
                "SOYEON-WIN": 7,
                "HYERYEONG-WIN": 4,
                "JUHO-WIN": 5,
            },
        },
    }
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://demo.example") as client:
        result = _verify_presentation(client, "token", manifest)

    assert result["chainIncidentAlertCount"] == 3
