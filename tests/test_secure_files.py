from pathlib import Path
from subprocess import CompletedProcess

from tools import secure_files


def test_posix_private_file_and_directory_modes(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    directory = tmp_path / "private"
    secret.write_text("secret", encoding="utf-8")
    directory.mkdir()

    secure_files.protect_private_path(secret)
    secure_files.protect_private_path(directory, directory=True)

    if secure_files.os.name != "nt":
        assert secret.stat().st_mode & 0o777 == 0o600
        assert directory.stat().st_mode & 0o777 == 0o700


def test_windows_acl_uses_current_user_and_system(monkeypatch, tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("secret", encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(secure_files, "_is_windows", lambda: True)
    monkeypatch.setattr(secure_files, "_current_windows_sid", lambda: "S-1-5-21-1234")

    def run(arguments, **_kwargs):
        calls.append(arguments)
        return CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(secure_files.subprocess, "run", run)
    secure_files.protect_private_path(secret)

    assert calls == [
        [
            "icacls",
            str(secret),
            "/inheritance:r",
            "/grant:r",
            "*S-1-5-21-1234:F",
            "*S-1-5-18:F",
        ]
    ]
