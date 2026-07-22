from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).parents[1]
DEFAULT_MANIFEST = ROOT / "runtime" / "demo" / "presentation-manifest.json"


def _request(client: httpx.Client, path: str, token: str) -> dict[str, Any]:
    response = client.get(path, headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    return response.json()["data"]


def _login(client: httpx.Client, login_id: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"loginId": login_id, "password": password},
    )
    response.raise_for_status()
    return str(response.json()["data"]["accessToken"])


def _verify_presentation(
    client: httpx.Client,
    token: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    counts = manifest["counts"]
    range_counts = manifest["rangeCounts"]
    ids = manifest["ids"]
    summary = _request(
        client,
        "/api/v1/dashboard/summary?timePreset=LATEST_24H&interval=5m",
        token,
    )
    latest_24h = {
        "endpoints": int(summary["endpoints"]["totalCount"]),
        "events": int(summary["events"]["totalCount"]),
        "alerts": int(summary["alerts"]["totalCount"]),
        "incidents": int(summary["incidents"]["openCount"]),
    }
    expected_24h = {
        "endpoints": counts["endpoints"],
        "events": range_counts["latest24h"],
        "alerts": counts["alerts"],
        "incidents": counts["incidents"],
    }
    if latest_24h != expected_24h:
        raise AssertionError(f"LATEST_24H Overview differs: expected={expected_24h}, actual={latest_24h}")
    summary_7d = _request(
        client,
        "/api/v1/dashboard/summary?timePreset=LATEST_7D&interval=1d",
        token,
    )
    latest_7d = {
        "endpoints": int(summary_7d["endpoints"]["totalCount"]),
        "events": int(summary_7d["events"]["totalCount"]),
        "alerts": int(summary_7d["alerts"]["totalCount"]),
        "incidents": int(summary_7d["incidents"]["openCount"]),
    }
    expected_7d = {**expected_24h, "events": range_counts["latest7d"]}
    if latest_7d != expected_7d:
        raise AssertionError(f"LATEST_7D Overview differs: expected={expected_7d}, actual={latest_7d}")

    powershell_incident_id = int(ids["powershellIncidentId"])
    egress_incident_id = int(ids["egressIncidentId"])
    powershell = _request(client, f"/api/v1/incidents/{powershell_incident_id}", token)
    egress = _request(client, f"/api/v1/incidents/{egress_incident_id}", token)
    if powershell["correlationKey"] != "suspicious-powershell" or powershell["alertCount"] != 2:
        raise AssertionError("PowerShell Incident must contain two suspicious-powershell Alerts")
    if egress["correlationKey"] != "suspicious-egress" or egress["alertCount"] != 1:
        raise AssertionError("Egress Alert must remain in its own suspicious-egress Incident")

    timeline = _request(
        client,
        f"/api/v1/incidents/{powershell_incident_id}/timeline",
        token,
    )
    if len(timeline["items"]) < 2:
        raise AssertionError("PowerShell Incident timeline does not expose both linked Alerts")
    main_endpoint_id = int(ids["presentationEndpointId"])
    endpoint = _request(client, f"/api/v1/endpoints/{main_endpoint_id}", token)
    if endpoint["hostname"] != "SOYEON-WIN":
        raise AssertionError("manifest presentationEndpointId points to the wrong Endpoint")
    if endpoint["risk"]["activeAlertCount"] != 3 or endpoint["risk"]["openIncidentCount"] != 2:
        raise AssertionError("main Endpoint must expose 3 active Alerts and 2 open Incidents")
    events = _request(
        client,
        f"/api/v1/events?timePreset=LATEST_24H&endpointId={main_endpoint_id}&page=1&size=100",
        token,
    )
    if events["total"] != 85:
        raise AssertionError(f"SOYEON-WIN LATEST_24H timeline expected 85 Events, got {events['total']}")
    expected_hostnames = {"GEONHA-MACMINI", "GEONHA-WIN", "SOYEON-WIN", "HYERYEONG-WIN", "JUHO-WIN"}
    actual_hostnames = set(ids["endpointIdsByHostname"])
    if actual_hostnames != expected_hostnames:
        raise AssertionError(f"Endpoint hostnames differ: expected={expected_hostnames}, actual={actual_hostnames}")
    return {
        "overviewLatest24h": latest_24h,
        "overviewLatest7d": latest_7d,
        "powershellIncidentAlertCount": powershell["alertCount"],
        "egressIncidentAlertCount": egress["alertCount"],
        "soyeonTimelineLatest24h": events["total"],
    }


def _verify_dns(client: httpx.Client, token: str, manifest: dict[str, Any]) -> dict[str, Any]:
    time_range = manifest["timeRange"]
    path = (
        "/api/v1/intelligence/correlate?value=yahoo.com"
        f"&timePreset=CUSTOM&from={time_range['from']}&to={time_range['to']}"
    )
    correlation = _request(client, path, token)
    observed = {str(correlation["inputValue"])}
    observed.update(str(item["value"]) for item in correlation["related"])
    for relationship in correlation["relationships"]:
        if "OBSERVED_EVENTS" in relationship["sources"]:
            observed.add(str(relationship["sourceValue"]))
            observed.add(str(relationship["targetValue"]))
    required = {"yahoo.com", "mail.yahoo.com", "api.yahoo.com"}
    excluded = {"notyahoo.com", "yahoo.com.evil.example", "yahoo.co"}
    if not required <= observed:
        raise AssertionError(f"missing exact/subdomain observations: {sorted(required - observed)}")
    if excluded & observed:
        raise AssertionError(f"false-positive domains returned: {sorted(excluded & observed)}")
    return {"included": sorted(required), "excluded": sorted(excluded)}


def verify(
    manifest_path: Path,
    *,
    api_base_url: str,
    login_id: str,
    password: str,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("mockData") is not True:
        raise AssertionError("manifest must explicitly mark the dataset as mock data")
    if manifest.get("ingestionMode") not in {"direct-seed", "collector-kafka"}:
        raise AssertionError("manifest ingestionMode is missing or invalid")
    with httpx.Client(base_url=api_base_url, timeout=15) as client:
        token = _login(client, login_id, password)
        if manifest["profile"] == "presentation":
            checks = _verify_presentation(client, token, manifest)
        elif manifest["profile"] == "dns-correctness":
            checks = _verify_dns(client, token, manifest)
        else:
            raise AssertionError(f"unsupported manifest profile: {manifest['profile']}")
    return {
        "profile": manifest["profile"],
        "ingestionMode": manifest["ingestionMode"],
        "verified": True,
        "checks": checks,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify an EDR_C presentation seed through the real Dashboard API.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--login-id", default="frontend-admin")
    parser.add_argument("--password", default="frontend-admin-password")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    try:
        result = verify(
            manifest_path,
            api_base_url=args.api_base_url,
            login_id=args.login_id,
            password=args.password,
        )
    except (OSError, ValueError, KeyError, AssertionError, httpx.HTTPError) as error:
        print(f"presentation demo verification failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
