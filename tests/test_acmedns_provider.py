"""Tests for the acme-dns DNS provider (mocked HTTP)."""

from __future__ import annotations

import json

import httpx
import pytest

from acme_lan.dns.acmedns import AcmeDnsProvider


def test_acmedns_publish_calls_update():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"txt": seen["body"]["txt"]})

    provider = AcmeDnsProvider(
        api_url="https://acme-dns.example/",
        username="user1",
        password="key1",
        subdomain="abc-123",
        transport=httpx.MockTransport(handler),
    )
    provider.publish_txt("_acme-challenge.db.example.net", "validation-value")

    assert seen["path"] == "/update"
    assert seen["headers"]["x-api-user"] == "user1"
    assert seen["headers"]["x-api-key"] == "key1"
    assert seen["body"] == {"subdomain": "abc-123", "txt": "validation-value"}
    # remove is a no-op (acme-dns self-expires)
    provider.remove_txt("_acme-challenge.db.example.net", "validation-value")


def test_acmedns_requires_full_config():
    with pytest.raises(ValueError):
        AcmeDnsProvider("", "", "", "")
