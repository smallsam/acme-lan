"""Tests for the management REST API and its optional admin-token gate."""

from __future__ import annotations

import os
from datetime import timedelta

import httpx

from acme_lan.models import utcnow


async def _seed_app(tmp_path, **env):
    # Clear toggles that other tests may have set, so each test starts clean.
    os.environ.pop("ACME_LAN_ADMIN_TOKEN", None)
    os.environ["ACME_LAN_EXTERNAL_URL"] = "http://localhost:8000"
    os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/mgmt.sqlite"
    for key, value in env.items():
        os.environ[key] = value

    from acme_lan import config, db

    config.reset_settings_cache()
    db._engine = None
    db._sessionmaker = None

    from acme_lan.db import init_db, session_scope
    from acme_lan.models import Certificate, Order

    await init_db()
    async with session_scope() as session:
        order = Order(
            account_id="acct-1",
            identifiers=[{"type": "dns", "value": "db.lan.test"}],
            status="valid",
        )
        session.add(order)
        await session.flush()
        cert = Certificate(
            order_id=order.id,
            pem_chain="-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
            serial="ab12",
            subject="CN=db.lan.test",
            not_after=utcnow() + timedelta(days=80),
        )
        session.add(cert)
        await session.flush()
        order.certificate_id = cert.id
        session.add(order)
        await session.commit()
        cert_id = cert.id

    from acme_lan.main import create_app

    return create_app(), cert_id


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_stats_and_certificate_listing(tmp_path):
    app, cert_id = await _seed_app(tmp_path)
    async with _client(app) as client:
        stats = (await client.get("/api/stats")).json()
        assert stats["certificates_total"] == 1
        assert stats["orders_by_status"]["valid"] == 1

        listing = (await client.get("/api/certificates")).json()
        assert listing["total"] == 1
        assert listing["limit"] == 25 and listing["offset"] == 0
        certs = listing["items"]
        assert len(certs) == 1
        assert certs[0]["primary_domain"] == "db.lan.test"
        assert certs[0]["id"] == cert_id

        detail = (await client.get(f"/api/certificates/{cert_id}")).json()
        assert "BEGIN CERTIFICATE" in detail["pem_chain"]


async def test_admin_token_gating(tmp_path):
    app, _ = await _seed_app(tmp_path, ACME_LAN_ADMIN_TOKEN="s3cret")
    async with _client(app) as client:
        assert (await client.get("/api/stats")).status_code == 401
        ok = await client.get("/api/stats", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200


async def test_probe_endpoint_reports_unreachable(tmp_path):
    app, _ = await _seed_app(tmp_path)
    async with _client(app) as client:
        resp = await client.post(
            "/api/health/probe", json={"host": "127.0.0.1", "port": 1, "server_name": None}
        )
        assert resp.status_code == 200
        assert resp.json()["reachable"] is False


async def test_certificate_health_uses_resolver_override(tmp_path):
    import json

    app, cert_id = await _seed_app(
        tmp_path,
        ACME_LAN_HEALTH_RESOLVER_OVERRIDES=json.dumps({"db.lan.test": "127.0.0.1:9"}),
    )
    async with _client(app) as client:
        health = (await client.get(f"/api/certificates/{cert_id}/health")).json()
    # The probe went to the override target (127.0.0.1:9, closed) rather than the domain.
    assert health["host"] == "127.0.0.1"
    assert health["port"] == 9
    assert health["reachable"] is False


async def test_dashboard_is_served(tmp_path):
    app, _ = await _seed_app(tmp_path)
    async with _client(app) as client:
        # ACME + API routes still work alongside the static mount.
        assert (await client.get("/acme/directory")).status_code == 200
        index = await client.get("/")
        # The built dashboard is served if it has been compiled (src/acme_lan/web/dist).
        assert index.status_code in (200, 404)


async def test_check_port_set_clear_and_persists_across_renewals(tmp_path):
    import json

    app, cert_id = await _seed_app(
        tmp_path,
        # Point the probe at loopback so tests don't resolve real domains.
        ACME_LAN_HEALTH_RESOLVER_OVERRIDES=json.dumps({"db.lan.test": "127.0.0.1"}),
    )
    async with _client(app) as client:
        # Set a check port; it shows up on the certificate view and steers the probe.
        resp = await client.put(f"/api/certificates/{cert_id}/check-port", json={"port": 8006})
        assert resp.status_code == 200
        assert resp.json()["check_port"] == 8006
        health = (await client.get(f"/api/certificates/{cert_id}/health")).json()
        assert health["port"] == 8006

        # An explicit query param still wins over the stored port.
        health = (await client.get(f"/api/certificates/{cert_id}/health?port=9")).json()
        assert health["port"] == 9

        # A renewal creates a new certificate row for the same hostname: the stored
        # check port carries over because it is keyed by domain, not certificate id.
        from datetime import timedelta

        from acme_lan.db import session_scope
        from acme_lan.models import Certificate, utcnow

        async with session_scope() as session:
            renewed = Certificate(
                pem_chain="-----BEGIN CERTIFICATE-----\nMIIC\n-----END CERTIFICATE-----\n",
                domains=["db.lan.test"],
                not_after=utcnow() + timedelta(days=90),
            )
            session.add(renewed)
            await session.commit()
            renewed_id = renewed.id
        renewed_view = (await client.get(f"/api/certificates/{renewed_id}")).json()
        assert renewed_view["check_port"] == 8006
        health = (await client.get(f"/api/certificates/{renewed_id}/health")).json()
        assert health["port"] == 8006

        # Clearing (port: null) falls back to the default port.
        resp = await client.put(f"/api/certificates/{cert_id}/check-port", json={"port": None})
        assert resp.status_code == 200
        assert resp.json()["check_port"] is None
        health = (await client.get(f"/api/certificates/{cert_id}/health")).json()
        assert health["port"] == 443

        # Out-of-range ports are rejected.
        resp = await client.put(f"/api/certificates/{cert_id}/check-port", json={"port": 0})
        assert resp.status_code == 422


async def test_certificate_details_and_download(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    app, seeded_cert_id = await _seed_app(tmp_path)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "web.lan.test"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Smallsam Labs"),
            x509.NameAttribute(NameOID.EMAIL_ADDRESS, "certs@lan.test"),
        ]
    )
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    pem = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(0xABCD)
        .not_valid_before(utcnow() - timedelta(days=1))
        .not_valid_after(utcnow() + timedelta(days=89))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("web.lan.test"), x509.DNSName("alt.lan.test")]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    ).public_bytes(serialization.Encoding.PEM).decode()

    from acme_lan.db import session_scope
    from acme_lan.models import Certificate

    async with session_scope() as session:
        row = Certificate(
            pem_chain=pem, domains=["web.lan.test"], not_after=utcnow() + timedelta(days=89)
        )
        session.add(row)
        await session.commit()
        row_id = row.id

    async with _client(app) as client:
        details = (await client.get(f"/api/certificates/{row_id}")).json()["details"]
        assert details["common_name"] == "web.lan.test"
        assert details["organization"] == "Smallsam Labs"
        assert details["email"] == "certs@lan.test"
        assert details["issuer"] == "CN=Test CA"
        assert details["serial"] == "abcd"
        assert details["sans"] == ["web.lan.test", "alt.lan.test"]
        assert details["not_before"] and details["not_after"]

        # The seed's placeholder PEM is unparseable: details is None, not an error.
        assert (await client.get(f"/api/certificates/{seeded_cert_id}")).json()["details"] is None

        resp = await client.get(f"/api/certificates/{row_id}/download")
        assert resp.status_code == 200
        assert resp.headers["content-disposition"] == (
            'attachment; filename="web.lan.test-chain.pem"'
        )
        assert "BEGIN CERTIFICATE" in resp.text


def _make_cert(cn: str, serial: int, issuer_cn: str, days: int = 80):
    """Generate a self-signed cert (PEM) + key PEM with a chosen serial and issuer name."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)]))
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(utcnow() - timedelta(days=1))
        .not_valid_after(utcnow() + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return (
        cert.public_bytes(serialization.Encoding.PEM).decode(),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode(),
    )


def _serve_tls(tmp_path, cert_pem: str, key_pem: str):
    """Serve ``cert_pem`` on a loopback TLS port so probe_tls has something real to read."""
    import socket
    import ssl
    import threading

    cert_file = tmp_path / "srv.pem"
    key_file = tmp_path / "srv.key"
    cert_file.write_text(cert_pem)
    key_file.write_text(key_pem)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert_file), str(key_file))

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)

    def _serve():
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            try:
                with ctx.wrap_socket(conn, server_side=True) as tls:
                    tls.recv(1)
            except Exception:  # noqa: BLE001 - probe closes mid-handshake; that's fine
                pass

    threading.Thread(target=_serve, daemon=True).start()
    return listener.getsockname()[1], listener


async def test_health_audits_served_certificate_against_issued(tmp_path):
    """A trusted-looking endpoint serving a cert we never issued must be flagged."""
    import json

    served_pem, served_key = _make_cert("db.lan.test", 0x9999, "Some Other CA")
    port, listener = _serve_tls(tmp_path, served_pem, served_key)
    try:
        app, cert_id = await _seed_app(
            tmp_path,
            ACME_LAN_HEALTH_RESOLVER_OVERRIDES=json.dumps(
                {"db.lan.test": f"127.0.0.1:{port}"}
            ),
        )
        # Replace the seed's placeholder PEM with a real cert acme-lan "issued".
        ours_pem, _ = _make_cert("db.lan.test", 0xABCD, "Test CA")
        from acme_lan.db import session_scope
        from acme_lan.models import Certificate

        async with session_scope() as session:
            row = await session.get(Certificate, cert_id)
            row.pem_chain = ours_pem
            row.serial = "abcd"
            session.add(row)
            await session.commit()

        async with _client(app) as client:
            health = (await client.get(f"/api/certificates/{cert_id}/health")).json()

        # Trust/expiry are reported independently of the deployment audit.
        assert health["reachable"] is True
        assert health["chain_trusted"] is False
        assert health["expired"] is False

        audit = health["deployment"]
        assert audit["status"] == "foreign"
        assert audit["matches_issued"] is False
        assert audit["latest_issued_serial"] == "abcd"
        assert [f["code"] for f in audit["findings"]] == ["third_party_issuer"]
    finally:
        listener.close()


async def test_health_audit_reports_ok_for_our_own_certificate(tmp_path):
    import json

    ours_pem, ours_key = _make_cert("db.lan.test", 0xABCD, "Test CA")
    port, listener = _serve_tls(tmp_path, ours_pem, ours_key)
    try:
        app, cert_id = await _seed_app(
            tmp_path,
            ACME_LAN_HEALTH_RESOLVER_OVERRIDES=json.dumps(
                {"db.lan.test": f"127.0.0.1:{port}"}
            ),
        )
        from acme_lan.db import session_scope
        from acme_lan.models import Certificate

        async with session_scope() as session:
            row = await session.get(Certificate, cert_id)
            row.pem_chain = ours_pem
            row.serial = "abcd"
            session.add(row)
            await session.commit()

        async with _client(app) as client:
            audit = (await client.get(f"/api/certificates/{cert_id}/health")).json()[
                "deployment"
            ]
        assert audit["status"] == "ok"
        assert audit["matches_latest"] is True
        assert audit["findings"] == []
        assert audit["renewal_overdue"] is False
    finally:
        listener.close()


async def test_download_leaf_and_chain(tmp_path):
    app, _ = await _seed_app(tmp_path)
    leaf_pem, _key = _make_cert("web.lan.test", 0x1234, "Test CA")
    intermediate, _key2 = _make_cert("Test CA", 0x5678, "Test Root")
    chain = leaf_pem + intermediate

    from acme_lan.db import session_scope
    from acme_lan.models import Certificate

    async with session_scope() as session:
        row = Certificate(
            pem_chain=chain, domains=["web.lan.test"], not_after=utcnow() + timedelta(days=80)
        )
        session.add(row)
        await session.commit()
        row_id = row.id

    async with _client(app) as client:
        full = await client.get(f"/api/certificates/{row_id}/download")
        assert full.status_code == 200
        assert full.headers["content-disposition"] == (
            'attachment; filename="web.lan.test-chain.pem"'
        )
        assert full.text.count("BEGIN CERTIFICATE") == 2

        leaf = await client.get(f"/api/certificates/{row_id}/download?kind=leaf")
        assert leaf.status_code == 200
        assert leaf.headers["content-disposition"] == (
            'attachment; filename="web.lan.test-cert.pem"'
        )
        assert leaf.text.count("BEGIN CERTIFICATE") == 1
        # The leaf download is the end-entity cert, not the intermediate.
        assert leaf.text.strip() == leaf_pem.strip()

        bogus = await client.get(f"/api/certificates/{row_id}/download?kind=bogus")
        assert bogus.status_code == 400


async def test_health_probes_the_managed_host_address(tmp_path):
    """A pushed certificate's domain often has no LAN A record; use the device address."""
    ours_pem, ours_key = _make_cert("switch.lan.test", 0xBEEF, "Test CA")
    port, listener = _serve_tls(tmp_path, ours_pem, ours_key)
    try:
        app, _ = await _seed_app(tmp_path)
        from acme_lan.db import session_scope
        from acme_lan.models import Certificate, ManagedHost

        async with session_scope() as session:
            host = ManagedHost(
                name="switch",
                domains=["switch.lan.test"],
                address="127.0.0.1",   # the device's real address
                port=port,
                deploy_plugin="cisco_ios",
            )
            session.add(host)
            await session.flush()
            cert = Certificate(
                host_id=host.id,
                pem_chain=ours_pem,
                domains=["switch.lan.test"],
                serial="beef",
                not_after=utcnow() + timedelta(days=80),
            )
            session.add(cert)
            await session.commit()
            cert_id = cert.id

        async with _client(app) as client:
            health = (await client.get(f"/api/certificates/{cert_id}/health")).json()
        # Probed the device address:port rather than trying to resolve switch.lan.test.
        assert health["host"] == "127.0.0.1"
        assert health["port"] == port
        assert health["reachable"] is True
        assert health["deployment"]["status"] == "ok"
    finally:
        listener.close()


async def _seed_history(tmp_path, count=3, domain="renewed.lan.test"):
    """Seed `count` certificates for one domain, oldest first, as renewals would."""
    app, _ = await _seed_app(tmp_path)
    from acme_lan.db import session_scope
    from acme_lan.models import Certificate

    ids = []
    async with session_scope() as session:
        for index in range(count):
            pem, _key = _make_cert(domain, 0x100 + index, "Test CA")
            row = Certificate(
                pem_chain=pem,
                domains=[domain],
                serial=format(0x100 + index, "x"),
                not_after=utcnow() + timedelta(days=30 + index),
                issued_at=utcnow() - timedelta(days=count - index),
            )
            session.add(row)
            await session.flush()
            ids.append(row.id)
        await session.commit()
    return app, ids


async def test_superseded_certificates_are_hidden_by_default(tmp_path):
    app, ids = await _seed_history(tmp_path, count=3)
    newest = ids[-1]
    async with _client(app) as client:
        default = (await client.get("/api/certificates?search=renewed")).json()
        assert [c["id"] for c in default["items"]] == [newest]
        assert default["total"] == 1

        everything = (
            await client.get("/api/certificates?search=renewed&include_superseded=true")
        ).json()
        assert everything["total"] == 3
        by_id = {c["id"]: c for c in everything["items"]}
        assert by_id[newest]["superseded"] is False
        assert all(by_id[old]["superseded"] is True for old in ids[:-1])


async def test_retiring_the_newest_promotes_the_previous_certificate(tmp_path):
    """Retired certs are out of service, so they must not keep hiding their predecessors."""
    app, ids = await _seed_history(tmp_path, count=2)
    async with _client(app) as client:
        await client.post(f"/api/certificates/{ids[-1]}/retire")
        listing = (await client.get("/api/certificates?search=renewed")).json()
    shown = [c["id"] for c in listing["items"]]
    assert ids[0] in shown, "the remaining live certificate should now be visible"


async def test_certificate_search_sort_and_paging(tmp_path):
    app, _ = await _seed_app(tmp_path)
    from acme_lan.db import session_scope
    from acme_lan.models import Certificate

    async with session_scope() as session:
        for index, name in enumerate(["alpha.lan.test", "beta.lan.test", "gamma.lan.test"]):
            pem, _key = _make_cert(name, 0x200 + index, "Test CA")
            session.add(
                Certificate(
                    pem_chain=pem,
                    domains=[name],
                    serial=format(0x200 + index, "x"),
                    not_after=utcnow() + timedelta(days=10 + index),
                    issued_at=utcnow() - timedelta(days=3 - index),
                )
            )
        await session.commit()

    async with _client(app) as client:
        # search matches the domain
        hits = (await client.get("/api/certificates?search=beta")).json()
        assert hits["total"] == 1
        assert hits["items"][0]["primary_domain"] == "beta.lan.test"

        # search matches the serial too
        assert (await client.get("/api/certificates?search=201")).json()["total"] == 1

        # sort by expiry ascending
        asc = (await client.get("/api/certificates?sort=not_after&order=asc&limit=100")).json()
        expiries = [c["not_after"] for c in asc["items"] if c["not_after"]]
        assert expiries == sorted(expiries)

        # Paging reports the full total and returns only the requested slice. Four certs
        # match: the three above plus the db.lan.test one the fixture seeds.
        page = (await client.get("/api/certificates?limit=2&offset=0&search=lan.test")).json()
        assert page["total"] == 4
        assert len(page["items"]) == 2
        second = (await client.get("/api/certificates?limit=2&offset=2&search=lan.test")).json()
        assert second["total"] == 4
        assert len(second["items"]) == 2
        assert {c["id"] for c in page["items"]}.isdisjoint({c["id"] for c in second["items"]})

        # limits are bounded
        assert (await client.get("/api/certificates?limit=0")).status_code == 422
        assert (await client.get("/api/certificates?limit=9999")).status_code == 422


async def test_host_search_sort_and_paging(tmp_path):
    app, _ = await _seed_app(tmp_path)
    from acme_lan.db import session_scope
    from acme_lan.models import ManagedHost

    async with session_scope() as session:
        for name, address, plugin in [
            ("switch-a", "192.0.2.1", "cisco_ios"),
            ("printer-b", "192.0.2.2", "ssh"),
            ("esxi-c", "192.0.2.3", "local"),
        ]:
            session.add(
                ManagedHost(
                    name=name, address=address, deploy_plugin=plugin,
                    domains=[f"{name}.lan.test"],
                )
            )
        await session.commit()

    async with _client(app) as client:
        listing = (await client.get("/api/hosts?sort=name&order=asc")).json()
        assert [h["name"] for h in listing["items"]] == ["esxi-c", "printer-b", "switch-a"]
        assert listing["total"] == 3

        desc = (await client.get("/api/hosts?sort=name&order=desc")).json()
        assert [h["name"] for h in desc["items"]] == ["switch-a", "printer-b", "esxi-c"]

        # search covers name, address, plugin and domains
        assert (await client.get("/api/hosts?search=cisco")).json()["total"] == 1
        assert (await client.get("/api/hosts?search=192.0.2.2")).json()["total"] == 1
        assert (await client.get("/api/hosts?search=printer-b.lan")).json()["total"] == 1

        page = (await client.get("/api/hosts?limit=2")).json()
        assert page["total"] == 3 and len(page["items"]) == 2
