from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path


def _is_windows() -> bool:
    return os.name == "nt"


def _current_windows_sid() -> str:
    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    )
    row = next(csv.reader([result.stdout.strip()]))
    sid = next((value for value in reversed(row) if value.upper().startswith("S-1-")), "")
    if not sid:
        raise RuntimeError("could not determine the current Windows user SID")
    return sid


def protect_private_path(path: Path, *, directory: bool = False) -> None:
    """Restrict a local secret to the current account (and SYSTEM on Windows)."""
    if not _is_windows():
        path.chmod(0o700 if directory else 0o600)
        return

    sid = _current_windows_sid()
    permission = "(OI)(CI)F" if directory else "F"
    subprocess.run(
        [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"*{sid}:{permission}",
            f"*S-1-5-18:{permission}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def set_public_file_mode(path: Path) -> None:
    if not _is_windows():
        path.chmod(0o644)
