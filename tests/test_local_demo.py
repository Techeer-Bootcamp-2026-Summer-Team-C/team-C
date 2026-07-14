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
    assert "EDR_ACCESS_TOKEN_TTL_SECONDS=43200" in first
    assert "NGINX_HTTP_HOST_PORT=8080" in first
    assert "NGINX_MTLS_HOST_PORT=8443" in first
    assert local_demo._write_local_env() is False
    assert env_file.read_text(encoding="utf-8") == first

    credentials = local_demo._ensure_credentials()
    assert credentials["loginId"] == "admin"
    assert len(credentials["password"]) >= 20
    assert json.loads((runtime / "credentials.json").read_text(encoding="utf-8")) == credentials


def test_migrates_legacy_email_credential_key(monkeypatch, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime" / "demo"
    credentials_file = runtime / "credentials.json"
    runtime.mkdir(parents=True)
    credentials_file.write_text('{"email":"legacy@example.com","password":"secret"}\n', encoding="utf-8")
    monkeypatch.setattr(local_demo, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(local_demo, "CREDENTIALS_FILE", credentials_file)

    credentials = local_demo._ensure_credentials()

    assert credentials == {"loginId": "legacy@example.com", "password": "secret"}
    assert json.loads(credentials_file.read_text(encoding="utf-8")) == credentials


def test_compose_uses_generated_env_file(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("EDR_ENV=local\n", encoding="utf-8")
    monkeypatch.setattr(local_demo, "ENV_FILE", env_file)
    monkeypatch.setattr(local_demo, "_tool", lambda name: name)

    assert local_demo._compose("up", "-d") == ["docker", "compose", "--env-file", str(env_file), "up", "-d"]
