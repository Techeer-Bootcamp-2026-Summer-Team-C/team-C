import json
from pathlib import Path

from tools import local_demo


def test_generates_gitignored_local_secrets_without_overwrite(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    runtime = tmp_path / "runtime" / "demo"
    monkeypatch.setattr(local_demo, "ENV_FILE", env_file)
    monkeypatch.setattr(local_demo, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(local_demo, "CREDENTIALS_FILE", runtime / "credentials.json")

    assert local_demo._write_local_env() is True
    first = env_file.read_text(encoding="utf-8")
    assert "replace-with" not in first
    assert "EDR_AGENT_CA_CERT_PATH=./certs/ca/ca.crt" in first
    assert local_demo._write_local_env() is False
    assert env_file.read_text(encoding="utf-8") == first

    credentials = local_demo._ensure_credentials()
    assert credentials["email"] == "admin@edr.local"
    assert len(credentials["password"]) >= 20
    assert json.loads((runtime / "credentials.json").read_text(encoding="utf-8")) == credentials


def test_demo_agent_id_is_contract_safe(monkeypatch) -> None:
    monkeypatch.setattr(local_demo.socket, "gethostname", lambda: "WIN DEV/#01")
    assert local_demo._agent_id() == "demo-win-dev--01"
