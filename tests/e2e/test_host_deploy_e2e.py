"""End-to-end: acme-lan issues a cert for a managed host via Pebble and deploys it.

This is the certgrinder-style path: acme-lan generates the key + CSR itself, obtains a
real cert from the upstream CA (DNS-01), and pushes both to the device (here, the local
filesystem plugin). Proves the deployed key matches the issued certificate.
"""

from __future__ import annotations

import os

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_private_key,
)
from cryptography.x509.oid import ExtensionOID


async def test_host_issuance_and_deploy_via_pebble(pebble, tmp_path):
    os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/hosts.sqlite"
    os.environ["ACME_LAN_UPSTREAM_DIRECTORY_URL"] = pebble["directory"]
    os.environ["ACME_LAN_UPSTREAM_VERIFY_SSL"] = "false"
    os.environ["ACME_LAN_DNS_PROVIDER"] = "challtestsrv"
    os.environ["ACME_LAN_CHALLTESTSRV_URL"] = pebble["challtestsrv"]
    os.environ["ACME_LAN_UPSTREAM_ACCOUNT_KEY_PATH"] = str(tmp_path / "acct.key")
    os.environ["ACME_LAN_SECRET_KEY"] = Fernet.generate_key().decode()

    from acme_lan import config, db

    config.reset_settings_cache()
    db._engine = None
    db._sessionmaker = None

    from acme_lan.db import init_db, session_scope
    from acme_lan.hosts import renew_and_deploy
    from acme_lan.models import ManagedHost

    await init_db()

    cert_path = tmp_path / "device-cert.pem"
    key_path = tmp_path / "device-key.pem"
    domain = "esxi01.lan.test"

    async with session_scope() as session:
        host = ManagedHost(
            name="esxi01",
            domains=[domain],
            address="127.0.0.1",
            deploy_plugin="local",
            config={"cert_path": str(cert_path), "key_path": str(key_path)},
        )
        session.add(host)
        await session.commit()
        cert, result = await renew_and_deploy(host, session)

    assert result.ok, result.detail

    # The device received a real chain covering its domain.
    chain = x509.load_pem_x509_certificates(cert_path.read_bytes())
    leaf = chain[0]
    san = leaf.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    assert domain in san.value.get_values_for_type(x509.DNSName)

    # The deployed private key matches the issued certificate.
    deployed_key = load_pem_private_key(key_path.read_bytes(), password=None)
    assert deployed_key.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    ) == leaf.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)

    assert cert.host_id == host.id
