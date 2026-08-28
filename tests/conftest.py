"""Shared pytest fixtures: a live acme-lan server, Pebble upstream, and helpers."""

from __future__ import annotations

import json as jsonlib
import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
import uvicorn
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

# Localhost traffic (our server, Pebble, challtestsrv) must never go through the agent
# proxy, or requests/httpx will fail to reach the loopback services.
for _var in ("NO_PROXY", "no_proxy"):
    _existing = os.environ.get(_var, "")
    _needed = "localhost,127.0.0.1,::1"
    os.environ[_var] = f"{_existing},{_needed}" if _existing else _needed

# Tests validate against a local mock DNS server (challtestsrv) where propagation is
# instant; don't inherit the real-world default wait.
os.environ.setdefault("ACME_LAN_DNS_PROPAGATION_SECONDS", "0")

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.test.yml"
PEBBLE_DIRECTORY = "https://localhost:14000/dir"
CHALLTESTSRV_URL = "http://localhost:8055"


@pytest.fixture(autouse=True)
def _isolate_env():
    """Restore os.environ after every test so ACME_LAN_* overrides don't leak."""
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_csr(domains: list[str]) -> tuple[bytes, rsa.RSAPrivateKey]:
    """Build a CSR (PEM bytes) + its private key for the given DNS names."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domains[0])]))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(d) for d in domains]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM), key


class ChallengeResponder:
    """A tiny HTTP server that answers http-01 requests for registered tokens."""

    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}
        self.port = _free_port()
        responder = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                token = self.path.rsplit("/", 1)[-1]
                content = responder._tokens.get(token)
                if content is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.end_headers()
                self.wfile.write(content.encode())

            def log_message(self, *args):  # silence
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def register(self, token: str, key_authorization: str) -> None:
        self._tokens[token] = key_authorization

    def stop(self) -> None:
        self._server.shutdown()


@pytest.fixture
def challenge_responder():
    responder = ChallengeResponder()
    responder.start()
    yield responder
    responder.stop()


def _wait_http(url: str, *, verify: bool = True, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            resp = httpx.get(url, verify=verify, timeout=2)
            if resp.status_code < 500:
                return
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last}")


@pytest.fixture
async def fresh_db(tmp_path):
    """Configure a clean temp database (+ a Fernet secret key) and initialise it.

    Tests use ``acme_lan.db.session_scope`` to seed rows and ``create_app`` for HTTP.
    """
    os.environ.pop("ACME_LAN_ADMIN_TOKEN", None)
    os.environ["ACME_LAN_EXTERNAL_URL"] = "http://localhost:8000"
    os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/fresh.sqlite"
    os.environ["ACME_LAN_SECRET_KEY"] = Fernet.generate_key().decode()

    from acme_lan import config, db

    config.reset_settings_cache()
    db._engine = None
    db._sessionmaker = None

    from acme_lan.db import init_db

    await init_db()
    yield
    # Dispose the engine on the current loop so aiosqlite threads don't outlive it.
    await db.reset_engine()


@pytest.fixture
def make_server(tmp_path):
    """Factory that starts a fresh acme-lan server (uvicorn thread) with given env."""
    started: list[uvicorn.Server] = []

    def _make(**env: str) -> str:
        port = _free_port()
        base = f"http://127.0.0.1:{port}"
        os.environ["ACME_LAN_EXTERNAL_URL"] = base
        os.environ["ACME_LAN_DATABASE_URL"] = (
            f"sqlite+aiosqlite:///{tmp_path}/db-{port}.sqlite"
        )
        for key, value in env.items():
            os.environ[key] = value

        from acme_lan import config, db

        config.reset_settings_cache()
        db._engine = None
        db._sessionmaker = None

        from acme_lan.main import create_app

        app = create_app()
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        _wait_http(f"{base}/healthz", timeout=15)
        started.append(server)
        return base

    yield _make

    for server in started:
        server.should_exit = True
    time.sleep(0.3)


def _find_binary(name: str, env_var: str) -> str | None:
    """Locate a Pebble binary via env override, PATH, or the usual Go bin dirs."""
    override = os.environ.get(env_var)
    if override and Path(override).exists():
        return override
    found = shutil.which(name)
    if found:
        return found
    for candidate_dir in ("/home/user/go/bin", os.path.expanduser("~/go/bin"), "/root/go/bin"):
        candidate = Path(candidate_dir) / name
        # os.path.exists (unlike Path.exists) returns False on unreadable dirs like /root.
        if os.path.exists(candidate):
            return str(candidate)
    return None


def _write_self_signed(dir_path: Path) -> tuple[Path, Path]:
    """Write a throwaway self-signed localhost cert for Pebble's HTTPS listener."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path = dir_path / "cert.pem"
    key_path = dir_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


@pytest.fixture(scope="session")
def pebble(tmp_path_factory):
    """Run Pebble + pebble-challtestsrv as native subprocesses for the test session.

    Prefers the locally-built Go binaries (see README: ``go install ...pebble`` and
    ``...pebble-challtestsrv``). Skips if the binaries aren't available.
    """
    pebble_bin = _find_binary("pebble", "PEBBLE_BIN")
    chall_bin = _find_binary("pebble-challtestsrv", "CHALLTESTSRV_BIN")
    if not (pebble_bin and chall_bin):
        pytest.skip(
            "pebble / pebble-challtestsrv binaries not found "
            "(build with: go install github.com/letsencrypt/pebble/v2/cmd/pebble@latest "
            "and .../cmd/pebble-challtestsrv@latest)"
        )

    workdir = tmp_path_factory.mktemp("pebble")
    cert_path, key_path = _write_self_signed(workdir)
    config = {
        "pebble": {
            "listenAddress": "0.0.0.0:14000",
            "managementListenAddress": "0.0.0.0:15000",
            "certificate": str(cert_path),
            "privateKey": str(key_path),
            "httpPort": 5002,
            "tlsPort": 5001,
            "ocspResponderURL": "",
            "externalAccountBindingRequired": False,
        }
    }
    config_path = workdir / "pebble-config.json"
    config_path.write_text(jsonlib.dumps(config))

    logs = open(workdir / "pebble.log", "w")  # noqa: SIM115
    # challtestsrv: only DNS (for DNS-01 TXT) + management; disable the others so
    # they don't collide with Pebble's ports.
    chall = subprocess.Popen(
        [
            chall_bin,
            "-dnsserver", ":8053",
            "-management", ":8055",
            "-http01", "",
            "-https01", "",
            "-tlsalpn01", "",
            "-doh", "",
            "-defaultIPv4", "",
            "-defaultIPv6", "",
        ],
        stdout=logs,
        stderr=subprocess.STDOUT,
    )
    pebble_proc = subprocess.Popen(
        [pebble_bin, "-config", str(config_path), "-dnsserver", "127.0.0.1:8053"],
        env={**os.environ, "PEBBLE_VA_NOSLEEP": "1"},
        stdout=logs,
        stderr=subprocess.STDOUT,
    )

    try:
        _wait_http(PEBBLE_DIRECTORY, verify=False, timeout=30)
    except Exception:
        pebble_proc.terminate()
        chall.terminate()
        logs.close()
        print((workdir / "pebble.log").read_text())
        raise

    yield {"directory": PEBBLE_DIRECTORY, "challtestsrv": CHALLTESTSRV_URL}

    pebble_proc.terminate()
    chall.terminate()
    for proc in (pebble_proc, chall):
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()
    logs.close()
