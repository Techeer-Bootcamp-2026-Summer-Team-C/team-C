from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Gateway(ThreadingHTTPServer):
    backend_host: str
    backend_port: int
    received_batch_ids: list[str]


class Handler(BaseHTTPRequestHandler):
    server: Gateway

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path.endswith("/collector/telemetry/batches"):
            payload = json.loads(body)
            self.server.received_batch_ids.append(payload["batchId"])
        certificate = self.connection.getpeercert()  # type: ignore[attr-defined]
        certificate_der = self.connection.getpeercert(binary_form=True)  # type: ignore[attr-defined]
        san_agent_id = ""
        for kind, value in certificate.get("subjectAltName", ()):  # pragma: no branch - 계약상 URI SAN은 하나다
            if kind == "URI" and value.startswith("urn:edr:agent:"):
                san_agent_id = value.removeprefix("urn:edr:agent:")
        subject = ",".join(f"{key}={value}" for part in certificate.get("subject", ()) for key, value in part)
        headers = {
            "Content-Type": self.headers.get("Content-Type", "application/json"),
            "X-Request-ID": self.headers.get("X-Request-ID", "req_agent_e2e_gateway"),
            "X-EDR-mTLS-Verify": "SUCCESS",
            "X-EDR-Certificate-Subject": subject,
            "X-EDR-Certificate-SAN-Agent-ID": san_agent_id,
            "X-EDR-Certificate-Fingerprint-SHA256": hashlib.sha256(certificate_der).hexdigest(),
            "X-EDR-Certificate-Not-Before": certificate["notBefore"],
            "X-EDR-Certificate-Not-After": certificate["notAfter"],
        }
        if self.headers.get("Content-Encoding") == "gzip":
            headers["Content-Encoding"] = "gzip"
        connection = http.client.HTTPConnection(self.server.backend_host, self.server.backend_port, timeout=30)
        try:
            connection.request("POST", self.path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() in {"content-type", "x-request-id"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        finally:
            connection.close()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def create_gateway(
    *,
    listen_host: str,
    listen_port: int,
    backend_host: str,
    backend_port: int,
    certificate: Path,
    private_key: Path,
    client_ca: Path,
) -> Gateway:
    server = Gateway((listen_host, listen_port), Handler)
    server.backend_host = backend_host
    server.backend_port = backend_port
    server.received_batch_ids = []
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, private_key)
    context.load_verify_locations(client_ca)
    context.verify_mode = ssl.CERT_REQUIRED
    server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test-only mTLS gateway for the real Collector integration flow.")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=58443)
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=58877)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--client-ca", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    gateway = create_gateway(
        listen_host=arguments.listen_host,
        listen_port=arguments.listen_port,
        backend_host=arguments.backend_host,
        backend_port=arguments.backend_port,
        certificate=arguments.certificate,
        private_key=arguments.private_key,
        client_ca=arguments.client_ca,
    )
    print(json.dumps({"status": "ready", "port": arguments.listen_port}), flush=True)
    gateway.serve_forever()


if __name__ == "__main__":
    main()
