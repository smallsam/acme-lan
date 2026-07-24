"""Tests for the DNS provider plugins."""

from __future__ import annotations

import json

import httpx
import pytest

from acme_lan.dns.challtestsrv import ChallTestSrvProvider
from acme_lan.dns.cloudflare import CloudflareError, CloudflareProvider


def test_cloudflare_publish_and_remove_txt():
    """Drive the Cloudflare provider against a mocked API and assert the API calls."""
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        path = request.url.path
        if path.endswith("/zones"):
            name = request.url.params.get("name")
            result = [{"id": "zone123"}] if name == "example.net" else []
            return httpx.Response(200, json={"success": True, "result": result})
        if request.method == "POST" and path.endswith("/zones/zone123/dns_records"):
            payload = json.loads(request.content)
            assert payload["type"] == "TXT"
            assert payload["name"] == "_acme-challenge.db.example.net"
            assert payload["content"] == "token-value"
            return httpx.Response(200, json={"success": True, "result": {"id": "rec1"}})
        if request.method == "GET" and path.endswith("/zones/zone123/dns_records"):
            return httpx.Response(
                200,
                json={"success": True, "result": [{"id": "rec1", "content": '"token-value"'}]},
            )
        if request.method == "DELETE":
            return httpx.Response(200, json={"success": True, "result": {"id": "rec1"}})
        return httpx.Response(404, json={"success": False, "errors": ["unexpected"]})

    provider = CloudflareProvider(
        "fake-token", api_base="https://api.test/client/v4", transport=httpx.MockTransport(handler)
    )
    provider.publish_txt("_acme-challenge.db.example.net", "token-value")
    provider.remove_txt("_acme-challenge.db.example.net", "token-value")

    methods = [m for m, _ in calls]
    assert "POST" in methods and "DELETE" in methods


def test_cloudflare_requires_token():
    with pytest.raises(CloudflareError):
        CloudflareProvider("")


def test_cloudflare_unknown_zone_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "result": []})

    provider = CloudflareProvider("t", transport=httpx.MockTransport(handler))
    with pytest.raises(CloudflareError):
        provider.publish_txt("_acme-challenge.db.example.net", "v")


def test_challtestsrv_publish_and_remove(pebble):
    """Against a live challtestsrv, publishing/removing a TXT record must not error."""
    provider = ChallTestSrvProvider(pebble["challtestsrv"])
    provider.publish_txt("_acme-challenge.lan.test", "some-validation")
    provider.remove_txt("_acme-challenge.lan.test", "some-validation")
