"""End-to-end: upstream fulfilment via edge HTTP-01 (the alternative to DNS-01).

Configures acme-lan to prove control to the upstream CA by answering http-01 from its edge
HTTP responder. Pebble resolves the identifier (via challtestsrv A record) to 127.0.0.1 and
connects to the edge server on its httpPort (5002), just like a real edge deployment behind
wildcard DNS.
"""

from __future__ import annotations

import os

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.x509.oid import ExtensionOID

# Pebble validates http-01 on this port (its config's httpPort).
PEBBLE_HTTP_PORT = "5002"


async def test_edge_http01_issuance_via_pebble(pebble, tmp_path):
    os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/edge.sqlite"
    os.environ["ACME_LAN_UPSTREAM_DIRECTORY_URL"] = pebble["directory"]
    os.environ["ACME_LAN_UPSTREAM_VERIFY_SSL"] = "false"
    os.environ["ACME_LAN_DNS_PROVIDER"] = "challtestsrv"
    os.environ["ACME_LAN_CHALLTESTSRV_URL"] = pebble["challtestsrv"]
    os.environ["ACME_LAN_UPSTREAM_ACCOUNT_KEY_PATH"] = str(tmp_path / "acct.key")
    os.environ["ACME_LAN_UPSTREAM_CHALLENGE"] = "http-01"
    os.environ["ACME_LAN_EDGE_HTTP_PORT"] = PEBBLE_HTTP_PORT
    os.environ["ACME_LAN_EDGE_PUBLIC_IP"] = "127.0.0.1"
    os.environ["ACME_LAN_SECRET_KEY"] = Fernet.generate_key().decode()

    from acme_lan import config, db

    config.reset_settings_cache()
    db._engine = None
    db._sessionmaker = None

    from acme_lan.db import init_db, session_scope
    from acme_lan.hosts import renew_and_deploy
    from acme_lan.models import ManagedHost

    await init_db()

    domain = "edge01.lan.test"
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"

    async with session_scope() as session:
        host = ManagedHost(
            name="edge01",
            domains=[domain],
            address="127.0.0.1",
            deploy_plugin="local",
            csr_source="local",
            config={"cert_path": str(cert_path), "key_path": str(key_path)},
        )
        session.add(host)
        await session.commit()
        _cert, result = await renew_and_deploy(host, session)

    assert result.ok, result.detail
    chain = x509.load_pem_x509_certificates(cert_path.read_bytes())
    san = chain[0].extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    assert domain in san.value.get_values_for_type(x509.DNSName)
