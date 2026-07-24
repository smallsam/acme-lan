"""Tests for expiry notification channels and the expiry scan."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx

from acme_lan.db import session_scope
from acme_lan.models import Certificate
from acme_lan.notifications import (
    Notification,
    NotificationChannel,
    PostmarkChannel,
    WebhookChannel,
    notify_expiring,
)


async def test_postmark_channel_sends_expected_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("x-postmark-server-token")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ErrorCode": 0})

    channel = PostmarkChannel(
        "tok-123", "certs@lan", "admin@lan", transport=httpx.MockTransport(handler)
    )
    ok = await channel.send(Notification("subj", "msg", {"x": 1}))
    assert ok
    assert seen["url"] == "https://api.postmarkapp.com/email"
    assert seen["token"] == "tok-123"
    assert seen["body"]["From"] == "certs@lan"
    assert seen["body"]["To"] == "admin@lan"
    assert seen["body"]["Subject"] == "subj"


async def test_webhook_channel_posts_json():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(204)

    channel = WebhookChannel("https://hook.lan/notify", transport=httpx.MockTransport(handler))
    ok = await channel.send(Notification("subj", "msg", {"cert": "abc"}))
    assert ok
    assert seen["body"] == {"subject": "subj", "message": "msg", "data": {"cert": "abc"}}


class _CaptureChannel(NotificationChannel):
    name = "capture"

    def __init__(self) -> None:
        self.notes: list[Notification] = []

    async def send(self, note: Notification) -> bool:
        self.notes.append(note)
        return True


async def test_notify_expiring_warns_once_per_cert(fresh_db):
    async with session_scope() as session:
        session.add(
            Certificate(
                host_id="h1",
                domains=["db.lan.test"],
                not_after=datetime.now(UTC) + timedelta(days=3),
            )
        )
        await session.commit()

    channel = _CaptureChannel()
    first = await notify_expiring(channels=[channel])
    assert first == 1
    assert "db.lan.test" in channel.notes[0].subject

    # A second run must not re-warn (dedup via expiry_warned_at).
    second = await notify_expiring(channels=[channel])
    assert second == 0
    assert len(channel.notes) == 1
