from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.provision_agent_cert import provision


def _certificate_text(path: Path) -> str:
    return subprocess.run(
        ["openssl", "x509", "-in", str(path), "-noout", "-text", "-dates", "-fingerprint", "-sha256"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is not installed")
def test_provisions_single_san_client_certificate_and_reuses_ca(tmp_path: Path) -> None:
    first = provision("agent-mac-001", tmp_path)
    first_fingerprint = first.fingerprint_sha256
    first_ca = first.ca_certificate.read_bytes()
    text = _certificate_text(first.certificate)
    assert text.count("URI:urn:edr:agent:agent-mac-001") == 1
    assert "TLS Web Client Authentication" in text
    assert "Not Before" in text and "Not After" in text
    if os.name != "nt":
        assert oct(os.stat(first.private_key).st_mode & 0o777) == "0o600"
        assert oct(os.stat(first.pkcs12_bundle).st_mode & 0o777) == "0o600"
    subprocess.run(
        ["openssl", "pkcs12", "-in", str(first.pkcs12_bundle), "-passin", "pass:", "-noout"],
        check=True,
        capture_output=True,
    )

    second = provision("agent-mac-001", tmp_path)
    assert second.ca_certificate.read_bytes() == first_ca
    assert second.fingerprint_sha256 != first_fingerprint


@pytest.mark.parametrize("agent_id", ["", "Agent-Mac", "-agent", "a" * 65, "agent/mac"])
def test_rejects_invalid_agent_id(agent_id: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        provision(agent_id, tmp_path)
