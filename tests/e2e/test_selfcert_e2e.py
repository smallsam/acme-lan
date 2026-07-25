"""End-to-end: acme-lan obtains its OWN certificate via Pebble (DNS-01)."""

from __future__ import annotations

import os

from cryptography import x509
from cryptography.x509.oid import ExtensionOID


async def test_service_certificate_issued_via_pebble(pebble, tmp_path):
    domain = "acme-lan.lan.test"
    os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/self.sqlite"
    os.environ["ACME_LAN_UPSTREAM_DIRECTORY_URL"] = pebble["directory"]
    os.environ["ACME_LAN_UPSTREAM_VERIFY_SSL"] = "false"
    os.environ["ACME_LAN_DNS_PROVIDER"] = "challtestsrv"
    os.environ["ACME_LAN_CHALLTESTSRV_URL"] = pebble["challtestsrv"]
    os.environ["ACME_LAN_UPSTREAM_ACCOUNT_KEY_PATH"] = str(tmp_path / "acct.key")
    os.environ["ACME_LAN_SERVICE_DOMAIN"] = domain
    os.environ["ACME_LAN_SELF_CERT_PATH"] = str(tmp_path / "svc.pem")
    os.environ["ACME_LAN_SELF_CERT_KEY_PATH"] = str(tmp_path / "svc.key")

    from acme_lan import config, db

    config.reset_settings_cache()
    db._engine = None
    db._sessionmaker = None

    from acme_lan.db import init_db
    from acme_lan.selfcert import ensure_service_certificate

    await init_db()
    issued = await ensure_service_certificate()
    assert issued is True

    chain = x509.load_pem_x509_certificates((tmp_path / "svc.pem").read_bytes())
    leaf = chain[0]
    san = leaf.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    assert domain in san.value.get_values_for_type(x509.DNSName)
    assert len(chain) >= 2  # leaf + issuer from Pebble
