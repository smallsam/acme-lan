"""Serve acme-lan with a rich seeded dataset for documentation screenshots.

Seeds several certificates (healthy, expiring, expired) and managed hosts, and stands up a
couple of local TLS endpoints so the dashboard's realtime health badges render for real.
Run via ``uv run python tests/screenshot_server.py`` (port 8124), then capture with
``src/acme_lan/web/scripts/screenshot.mjs``.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import ssl
import tempfile
import threading
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

PORT = int(os.environ.get("ACME_LAN_UI_PORT", "8124"))
DB_PATH = os.path.join(tempfile.gettempdir(), "acme_lan_screenshot.db")
_tmp = tempfile.mkdtemp(prefix="acme-lan-shots-")


def _self_signed(domain: str, days: int) -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Let's Encrypt (test)")]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_file = os.path.join(_tmp, f"{domain}.crt")
    key_file = os.path.join(_tmp, f"{domain}.key")
    with open(cert_file, "wb") as fh:
        fh.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_file, "wb") as fh:
        fh.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    return cert_file, key_file


class TlsServer:
    def __init__(self, cert_file: str, key_file: str) -> None:
        self._ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._ctx.load_cert_chain(cert_file, key_file)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self._sock.settimeout(0.5)
        self.port = self._sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                continue
            try:
                self._ctx.wrap_socket(conn, server_side=True).close()
            except Exception:  # noqa: BLE001
                pass


# Reachable endpoints so a couple of health badges are live (green + amber).
HEALTHY = TlsServer(*_self_signed("db.lan.test", days=74))
EXPIRING = TlsServer(*_self_signed("esxi01.lan.test", days=11))

os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"
os.environ["ACME_LAN_EXTERNAL_URL"] = f"http://127.0.0.1:{PORT}"
os.environ["ACME_LAN_HEALTH_RESOLVER_OVERRIDES"] = json.dumps(
    {"db.lan.test": f"127.0.0.1:{HEALTHY.port}", "esxi01.lan.test": f"127.0.0.1:{EXPIRING.port}"}
)
os.environ.pop("ACME_LAN_ADMIN_TOKEN", None)
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

from acme_lan import config  # noqa: E402

config.reset_settings_cache()


async def _seed() -> None:
    from acme_lan.db import init_db, reset_engine, session_scope
    from acme_lan.models import Account, Certificate, ManagedHost, Order, utcnow

    await init_db()
    now = utcnow()
    async with session_scope() as session:
        # An external ACME client account + a couple of orders (for the stats row).
        session.add(Account(key_thumbprint="demo", jwk={"kty": "demo"}))
        for value, status in (("db.lan.test", "valid"), ("wiki.lan.test", "valid")):
            session.add(
                Order(account_id="x", identifiers=[{"type": "dns", "value": value}], status=status)
            )
        certs = [
            ("db.lan.test", 74),        # healthy (reachable)
            ("esxi01.lan.test", 11),    # expiring soon (reachable)
            ("wiki.lan.test", 45),      # healthy but not reachable -> "unreachable"
            ("old-app.lan.test", -3),   # expired
        ]
        for domain, days in certs:
            session.add(
                Certificate(
                    domains=[domain],
                    subject=f"CN={domain}",
                    serial=f"{abs(days):02x}ffee",
                    not_after=now + timedelta(days=days),
                )
            )
        hosts = [
            ("esxi01", ["esxi01.lan.test"], "192.168.3.5", "ssh", "device", "deployed"),
            ("printer-hp", ["printer.lan.test"], "192.168.3.20", "ssh", "device", "deployed"),
            ("switch-core", ["switch.lan.test"], "192.168.3.1", "ssh", "local", None),
        ]
        for name, domains, addr, plugin, csr, status in hosts:
            session.add(
                ManagedHost(
                    name=name, domains=domains, address=addr, deploy_plugin=plugin,
                    csr_source=csr, last_status=status,
                    last_deployed_at=now if status else None,
                )
            )
        await session.commit()
    await reset_engine()


def main() -> None:
    asyncio.run(_seed())
    import uvicorn

    uvicorn.run("acme_lan.main:app", host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
