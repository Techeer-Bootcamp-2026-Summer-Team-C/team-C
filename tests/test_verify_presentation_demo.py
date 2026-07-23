import io
from unittest.mock import Mock

import httpx
import pytest

from tools.verify_presentation_demo import _verify_presentation, main


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


def test_verifier_can_prompt_for_password_without_putting_it_in_arguments(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    verify = Mock(return_value={"profile": "presentation", "verified": True})
    monkeypatch.setattr("tools.verify_presentation_demo.verify", verify)
    monkeypatch.setattr("tools.verify_presentation_demo.getpass.getpass", lambda _: "private-password")

    assert (
        main(
            [
                "--manifest",
                "/tmp/presentation-manifest.json",
                "--api-base-url",
                "https://api.tukproject.dev",
                "--login-id",
                "mentor-review",
                "--prompt-password",
            ]
        )
        == 0
    )

    assert verify.call_args.kwargs["password"] == "private-password"
    assert "private-password" not in capsys.readouterr().out


def test_verifier_can_read_one_password_line_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    verify = Mock(return_value={"profile": "presentation", "verified": True})
    monkeypatch.setattr("tools.verify_presentation_demo.verify", verify)
    monkeypatch.setattr(
        "tools.verify_presentation_demo.sys.stdin",
        io.StringIO("stdin-password\nignored\n"),
    )

    assert main(["--password-stdin"]) == 0
    assert verify.call_args.kwargs["password"] == "stdin-password"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--api-base-url", "https://api.tukproject.dev"],
        ["--api-base-url", "https://api.tukproject.dev", "--password", "visible-password"],
    ],
)
def test_remote_verifier_rejects_default_or_plaintext_argument_passwords(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
) -> None:
    verify = Mock()
    monkeypatch.setattr("tools.verify_presentation_demo.verify", verify)

    assert main(arguments) == 2
    verify.assert_not_called()


def test_verifier_password_stdin_rejects_an_interactive_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = io.StringIO("visible-password\n")
    verify = Mock()
    monkeypatch.setattr(terminal, "isatty", lambda: True)
    monkeypatch.setattr("tools.verify_presentation_demo.sys.stdin", terminal)
    monkeypatch.setattr("tools.verify_presentation_demo.verify", verify)

    assert main(["--password-stdin"]) == 2
    verify.assert_not_called()
