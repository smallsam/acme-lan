"""Tests for the realtime TLS health probe."""

from __future__ import annotations

import asyncio
import ssl

import pytest

from acme_lan.health import probe_tls

from .conftest import _free_port, _write_self_signed


@pytest.fixture
async def tls_server(tmp_path):
    """Start a throwaway TLS server with a self-signed localhost cert."""
    cert_path, key_path = _write_self_signed(tmp_path)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert_path), str(key_path))
    port = _free_port()

    async def handle(reader, writer):
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", port, ssl=ctx)
    async with server:
        await server.start_serving()
        yield port


async def test_probe_reads_self_signed_cert(tls_server):
    health = await probe_tls("127.0.0.1", tls_server, server_name="localhost")
    assert health.reachable is True
    assert health.expired is False
    assert health.self_signed is True
    assert health.chain_trusted is False  # self-signed, not in the system trust store
    assert health.days_remaining is not None and health.days_remaining > 300
    assert "localhost" in (health.san or [])
    assert health.name_matches is True


async def test_probe_unreachable_port():
    health = await probe_tls("127.0.0.1", _free_port(), timeout=2.0)
    assert health.reachable is False
    assert health.error
