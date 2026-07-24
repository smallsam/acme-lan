"""Expiry-warning notifications over pluggable channels (Postmark email + webhook)."""

from __future__ import annotations

import abc
import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .certlifecycle import expiring_certificates, expiry_info
from .config import Settings, get_settings
from .db import session_scope
from .models import utcnow

logger = logging.getLogger("acme_lan.notifications")


@dataclass
class Notification:
    subject: str
    message: str
    data: dict[str, Any]


class NotificationChannel(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def send(self, note: Notification) -> bool:
        """Deliver a notification; return True on success."""


class PostmarkChannel(NotificationChannel):
    name = "postmark"

    def __init__(
        self,
        server_token: str,
        sender: str,
        recipients: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.server_token = server_token
        self.sender = sender
        self.recipients = recipients
        self._transport = transport

    async def send(self, note: Notification) -> bool:
        payload = {
            "From": self.sender,
            "To": self.recipients,
            "Subject": note.subject,
            "TextBody": note.message,
            "MessageStream": "outbound",
        }
        async with httpx.AsyncClient(timeout=20, transport=self._transport) as client:
            resp = await client.post(
                "https://api.postmarkapp.com/email",
                headers={
                    "X-Postmark-Server-Token": self.server_token,
                    "Accept": "application/json",
                },
                json=payload,
            )
        if resp.status_code >= 300:
            logger.warning("Postmark send failed: %s %s", resp.status_code, resp.text)
            return False
        return True


class WebhookChannel(NotificationChannel):
    name = "webhook"

    def __init__(self, url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url = url
        self._transport = transport

    async def send(self, note: Notification) -> bool:
        body = {"subject": note.subject, "message": note.message, "data": note.data}
        async with httpx.AsyncClient(timeout=20, transport=self._transport) as client:
            resp = await client.post(self.url, json=body)
        if resp.status_code >= 300:
            logger.warning("Webhook send failed: %s", resp.status_code)
            return False
        return True


def get_channels(settings: Settings | None = None) -> list[NotificationChannel]:
    settings = settings or get_settings()
    channels: list[NotificationChannel] = []
    if settings.postmark_server_token and settings.notify_email_from and settings.notify_email_to:
        channels.append(
            PostmarkChannel(
                settings.postmark_server_token,
                settings.notify_email_from,
                settings.notify_email_to,
            )
        )
    if settings.notify_webhook_url:
        channels.append(WebhookChannel(settings.notify_webhook_url))
    return channels


async def send_notification(
    note: Notification, channels: list[NotificationChannel] | None = None
) -> int:
    """Send ``note`` on every configured channel; return the number that succeeded."""
    channels = channels if channels is not None else get_channels()
    sent = 0
    for channel in channels:
        try:
            if await channel.send(note):
                sent += 1
        except Exception:  # noqa: BLE001 - one channel failing must not block others
            logger.warning("Notification channel %s failed", channel.name, exc_info=True)
    return sent


async def notify_expiring(channels: list[NotificationChannel] | None = None) -> int:
    """Warn about certificates newly expiring; return the count warned about.

    Each certificate is warned about once (a renewal is a new row, warned afresh).
    """
    settings = get_settings()
    channels = channels if channels is not None else get_channels()
    if not channels:
        return 0

    warned = 0
    async with session_scope() as session:
        certs = await expiring_certificates(session, settings.expiry_warn_days)
        for cert in certs:
            if cert.expiry_warned_at is not None:
                continue
            info = expiry_info(cert, settings.expiry_warn_days)
            domains = ", ".join(cert.domains or [cert.subject or cert.id])
            days = info["days_until_expiry"]
            state = "has EXPIRED" if info["expired"] else f"expires in {days} day(s)"
            note = Notification(
                subject=f"[acme-lan] Certificate for {domains} {state}",
                message=(
                    f"The certificate for {domains} {state} "
                    f"(not_after={cert.not_after}).\n"
                    f"Renew it, or retire it in acme-lan if it is no longer required."
                ),
                data={
                    "certificate_id": cert.id,
                    "domains": cert.domains,
                    "not_after": cert.not_after.isoformat() if cert.not_after else None,
                    "days_until_expiry": days,
                    "expired": info["expired"],
                },
            )
            if await send_notification(note, channels) > 0:
                cert.expiry_warned_at = utcnow()
                session.add(cert)
                warned += 1
        await session.commit()
    return warned


async def run_notifier(stop_event: asyncio.Event) -> None:
    """Loop until ``stop_event`` is set, sending expiry warnings each interval."""
    interval = get_settings().notify_check_interval_seconds
    logger.info("Expiry notifier started (every %ss)", interval)
    while not stop_event.is_set():
        try:
            await notify_expiring()
        except Exception:  # noqa: BLE001
            logger.exception("Expiry notification tick failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            pass
    logger.info("Expiry notifier stopped")
