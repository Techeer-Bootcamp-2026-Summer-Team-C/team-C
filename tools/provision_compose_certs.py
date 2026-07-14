from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.provision_agent_cert import _openssl, provision
from tools.secure_files import protect_private_path, set_public_file_mode


def _run(*arguments: str) -> None:
    subprocess.run(arguments, check=True, capture_output=True, text=True)


def _ensure_demo_agent(authority_directory: Path, agent_id: str) -> None:
    agent_directory = authority_directory / "agents" / agent_id
    expected = (
        agent_directory / "agent.crt",
        agent_directory / "agent.key",
        agent_directory / "agent.p12",
        agent_directory / "ca.crt",
    )
    if any(path.exists() for path in expected) and not all(path.exists() for path in expected):
        raise RuntimeError("demo Agent certificate bundle is incomplete")
    if not all(path.exists() for path in expected):
        provision(agent_id, authority_directory)


def _write_nginx_certificate(authority_directory: Path, nginx_directory: Path) -> None:
    ca_key = authority_directory / "ca" / "ca.key"
    ca_certificate = authority_directory / "ca" / "ca.crt"
    if not ca_key.exists() or not ca_certificate.exists():
        raise RuntimeError("development Agent CA was not created")

    nginx_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    protect_private_path(nginx_directory, directory=True)
    server_key = nginx_directory / "server.key"
    server_certificate = nginx_directory / "server.crt"

    with tempfile.TemporaryDirectory(prefix="edr-nginx-cert-") as temporary_directory:
        temporary = Path(temporary_directory)
        generated_key = temporary / "server.key"
        generated_certificate = temporary / "server.crt"
        csr = temporary / "server.csr"
        extensions = temporary / "server-extensions.cnf"
        extensions.write_text(
            "[server]\n"
            "basicConstraints=critical,CA:FALSE\n"
            "subjectAltName=DNS:localhost,DNS:nginx,IP:127.0.0.1\n"
            "extendedKeyUsage=serverAuth\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n",
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
            "/CN=localhost",
            "-keyout",
            str(generated_key),
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
            "server",
            "-out",
            str(generated_certificate),
        )
        shutil.copyfile(generated_key, server_key)
        shutil.copyfile(generated_certificate, server_certificate)

    shutil.copyfile(ca_certificate, nginx_directory / "agent-ca.crt")
    protect_private_path(server_key)
    set_public_file_mode(server_certificate)
    set_public_file_mode(nginx_directory / "agent-ca.crt")


def provision_compose_certificates(
    authority_directory: Path, nginx_directory: Path, demo_agent_id: str
) -> None:
    authority_directory = authority_directory.resolve()
    nginx_directory = nginx_directory.resolve()
    _ensure_demo_agent(authority_directory, demo_agent_id)
    _write_nginx_certificate(authority_directory, nginx_directory)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision local Compose mTLS certificates.")
    parser.add_argument("--authority-dir", type=Path, required=True)
    parser.add_argument("--nginx-dir", type=Path, required=True)
    parser.add_argument("--demo-agent-id", default="compose-demo-agent")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        provision_compose_certificates(arguments.authority_dir, arguments.nginx_dir, arguments.demo_agent_id)
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Compose certificate provisioning failed: {error}", file=sys.stderr)
        return 2
    print(f"nginxCertificates={arguments.nginx_dir.resolve()}")
    print(f"demoAgentCertificates={(arguments.authority_dir / 'agents' / arguments.demo_agent_id).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
