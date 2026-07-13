from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tools.secure_files import protect_private_path, set_public_file_mode

AGENT_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")


@dataclass(frozen=True)
class ProvisionedCertificate:
    agent_id: str
    certificate: Path
    private_key: Path
    ca_certificate: Path
    pkcs12_bundle: Path
    fingerprint_sha256: str


def _run(*arguments: str) -> None:
    subprocess.run(arguments, check=True, capture_output=True, text=True)


def _openssl() -> str:
    executable = shutil.which("openssl")
    if executable is None:
        raise RuntimeError("openssl is required to provision Agent certificates")
    return executable


def _fingerprint(path: Path) -> str:
    result = subprocess.run(
        [_openssl(), "x509", "-in", str(path), "-outform", "DER"],
        check=True,
        capture_output=True,
    )
    return hashlib.sha256(result.stdout).hexdigest().upper()


def _ensure_ca(root: Path) -> tuple[Path, Path]:
    ca_directory = root / "ca"
    ca_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    protect_private_path(ca_directory, directory=True)
    ca_key = ca_directory / "ca.key"
    ca_certificate = ca_directory / "ca.crt"
    if ca_key.exists() != ca_certificate.exists():
        raise RuntimeError("development CA is incomplete; restore or remove the CA directory")
    if not ca_key.exists():
        _run(
            _openssl(),
            "req",
            "-x509",
            "-newkey",
            "rsa:3072",
            "-sha256",
            "-nodes",
            "-days",
            "3650",
            "-subj",
            "/CN=EDR C Development Agent CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-keyout",
            str(ca_key),
            "-out",
            str(ca_certificate),
        )
    protect_private_path(ca_key)
    set_public_file_mode(ca_certificate)
    return ca_key, ca_certificate


def provision(agent_id: str, output_directory: Path) -> ProvisionedCertificate:
    if AGENT_ID_PATTERN.fullmatch(agent_id) is None:
        raise ValueError("agentId must match [a-z0-9][a-z0-9._-]{0,63}")

    root = output_directory.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    protect_private_path(root, directory=True)
    ca_key, ca_certificate = _ensure_ca(root)
    agent_directory = root / "agents" / agent_id
    agent_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    protect_private_path(agent_directory, directory=True)
    agent_key = agent_directory / "agent.key"
    agent_certificate = agent_directory / "agent.crt"
    deployed_ca = agent_directory / "ca.crt"
    pkcs12_bundle = agent_directory / "agent.p12"

    with tempfile.TemporaryDirectory(prefix="edr-agent-cert-") as temporary_directory:
        csr = Path(temporary_directory) / "agent.csr"
        extensions = Path(temporary_directory) / "agent-extensions.cnf"
        extensions.write_text(
            "[agent]\n"
            "basicConstraints=critical,CA:FALSE\n"
            f"subjectAltName=URI:urn:edr:agent:{agent_id}\n"
            "extendedKeyUsage=clientAuth\n"
            "keyUsage=critical,digitalSignature\n",
            encoding="utf-8",
        )
        _run(
            _openssl(),
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-nodes",
            "-subj",
            f"/CN={agent_id}",
            "-addext",
            f"subjectAltName=URI:urn:edr:agent:{agent_id}",
            "-addext",
            "extendedKeyUsage=clientAuth",
            "-addext",
            "keyUsage=critical,digitalSignature",
            "-keyout",
            str(agent_key),
            "-out",
            str(csr),
        )
        serial = ca_certificate.with_suffix(".srl")
        serial_arguments = ("-CAserial", str(serial)) if serial.exists() else ("-CAcreateserial",)
        _run(
            _openssl(),
            "x509",
            "-req",
            "-in",
            str(csr),
            "-CA",
            str(ca_certificate),
            "-CAkey",
            str(ca_key),
            *serial_arguments,
            "-days",
            "365",
            "-sha256",
            "-extfile",
            str(extensions),
            "-extensions",
            "agent",
            "-out",
            str(agent_certificate),
        )

    shutil.copyfile(ca_certificate, deployed_ca)
    _run(
        _openssl(),
        "pkcs12",
        "-export",
        "-out",
        str(pkcs12_bundle),
        "-inkey",
        str(agent_key),
        "-in",
        str(agent_certificate),
        "-certfile",
        str(ca_certificate),
        "-passout",
        "pass:",
    )
    protect_private_path(agent_key)
    set_public_file_mode(agent_certificate)
    set_public_file_mode(deployed_ca)
    protect_private_path(pkcs12_bundle)
    return ProvisionedCertificate(
        agent_id=agent_id,
        certificate=agent_certificate,
        private_key=agent_key,
        ca_certificate=deployed_ca,
        pkcs12_bundle=pkcs12_bundle,
        fingerprint_sha256=_fingerprint(agent_certificate),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision a development mTLS certificate for one EDR Agent.")
    parser.add_argument("--agent-id", required=True, help="Agent ID matching [a-z0-9][a-z0-9._-]{0,63}")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.getenv("EDR_CERT_OUTPUT_DIR", "certs")),
        help="Local secret output directory (default: EDR_CERT_OUTPUT_DIR or ./certs)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        certificate = provision(arguments.agent_id, arguments.output_dir)
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"certificate provisioning failed: {error}", file=sys.stderr)
        return 2
    print(f"agentId={certificate.agent_id}")
    print(f"certificate={certificate.certificate}")
    print(f"privateKey={certificate.private_key}")
    print(f"caCertificate={certificate.ca_certificate}")
    print(f"pkcs12Bundle={certificate.pkcs12_bundle}")
    print(f"fingerprintSha256={certificate.fingerprint_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
