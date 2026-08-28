"""Orchestrate an upstream order: DNS-01 fulfilment + finalize with the client's CSR.

This is the proxy core. Given the internal client's CSR we run a full order against the
upstream CA, prove control of each identifier by publishing a ``_acme-challenge`` TXT
record, and return the issued chain. The upstream cert is issued for the *client's* key
because we forward the client's CSR verbatim to the upstream finalize.
"""

from __future__ import annotations

import datetime
import logging
import time

from acme import challenges, messages

from ..config import get_settings
from ..dns.factory import get_dns_provider
from .client import build_client

logger = logging.getLogger("acme_lan.upstream")


def _select_challenge(
    authz: messages.AuthorizationResource, chall_cls
) -> messages.ChallengeBody:
    for challb in authz.body.challenges:
        if isinstance(challb.chall, chall_cls):
            return challb
    raise RuntimeError(
        f"Upstream offered no {chall_cls.typ} challenge for {authz.body.identifier.value!r}"
    )


def fulfil_order(csr_pem: str, upstream=None) -> str:
    """Obtain a certificate chain for the given CSR from the profile's upstream.

    ``upstream`` is a :class:`acme_lan.acme.profiles.ProfileUpstream`; when omitted the
    default profile (global settings, ACME upstream) is used. Dispatches to a private-CA
    handler (upstream_type=ca_handler) or the ACME upstream (dns-01 / edge http-01).
    """
    settings = get_settings()
    if upstream is not None and upstream.upstream_type == "ca_handler":
        from ..ca.factory import get_ca_handler

        handler = get_ca_handler(upstream.ca_handler, upstream.ca_handler_config)
        return handler.enroll(csr_pem)

    if settings.upstream_challenge == "http-01":
        return _fulfil_http01(csr_pem, settings, upstream)
    return _fulfil_dns01(csr_pem, settings, upstream)


def _client_kwargs(upstream) -> dict:
    if upstream is None:
        return {}
    return {
        "directory_url": upstream.directory_url,
        "verify_ssl": upstream.verify_ssl,
        "account_key_path": upstream.account_key_path,
        "account_email": upstream.account_email,
        "eab_kid": upstream.eab_kid,
        "eab_hmac_key": upstream.eab_hmac_key,
    }


def _log_authz_failures(acme_client, orderr) -> None:
    """Best-effort: surface per-authorization failure details after a failed order.

    ``finalize_order`` reports only "the order failed" — the actual reason (bad TXT,
    CAA, timeout...) lives on the authorizations' challenges.
    """
    try:
        for authz in orderr.authorizations:
            updated, _ = acme_client.poll(authz)
            body = updated.body
            errors_seen = False
            for challb in body.challenges:
                if challb.error:
                    errors_seen = True
                    logger.error(
                        "Upstream authz %s: %s challenge failed: %s",
                        body.identifier.value,
                        challb.typ,
                        challb.error,
                    )
            if not errors_seen:
                logger.error(
                    "Upstream authz %s finished in status %s", body.identifier.value, body.status
                )
    except Exception:  # noqa: BLE001 - diagnostics only
        logger.warning("Could not fetch authorization failure details", exc_info=True)


def _fulfil_dns01(csr_pem: str, settings, upstream=None) -> str:
    acme_client, account_key = build_client(settings, **_client_kwargs(upstream))
    provider = get_dns_provider(settings)

    orderr = acme_client.new_order(csr_pem.encode("ascii"))

    # (challenge_body, response, record_name, txt_value)
    work: list[tuple[messages.ChallengeBody, object, str, str]] = []
    try:
        for authz in orderr.authorizations:
            domain = authz.body.identifier.value
            challb = _select_challenge(authz, challenges.DNS01)
            response, validation = challb.chall.response_and_validation(account_key)
            record_name = f"_acme-challenge.{domain}"
            logger.info("Publishing TXT %s for upstream dns-01", record_name)
            provider.publish_txt(record_name, validation)
            work.append((challb, response, record_name, validation))

        if settings.dns_propagation_seconds:
            time.sleep(settings.dns_propagation_seconds)

        for challb, response, _, _ in work:
            acme_client.answer_challenge(challb, response)

        deadline = datetime.datetime.now() + datetime.timedelta(
            seconds=settings.upstream_finalize_timeout
        )
        try:
            finalized = acme_client.finalize_order(orderr, deadline)
        except Exception:
            _log_authz_failures(acme_client, orderr)
            raise
        return finalized.fullchain_pem
    finally:
        for _, _, record_name, validation in work:
            try:
                provider.remove_txt(record_name, validation)
            except Exception:  # noqa: BLE001 - cleanup is best-effort
                logger.warning("Failed to clean up TXT %s", record_name, exc_info=True)


def _fulfil_http01(csr_pem: str, settings, upstream=None) -> str:
    """Fulfil the upstream order via edge http-01: answer from a local edge HTTP server."""
    from .edge import EdgeHttpResponder

    acme_client, account_key = build_client(settings, **_client_kwargs(upstream))
    provider = get_dns_provider(settings)
    orderr = acme_client.new_order(csr_pem.encode("ascii"))

    edge = EdgeHttpResponder(settings.edge_http_port)
    edge.start()
    work: list[tuple[messages.ChallengeBody, object]] = []
    published_a: list[str] = []
    try:
        for authz in orderr.authorizations:
            domain = authz.body.identifier.value
            challb = _select_challenge(authz, challenges.HTTP01)
            response, validation = challb.chall.response_and_validation(account_key)
            token = challb.chall.encode("token")
            edge.register(token, validation)
            # If the provider can publish A records and an edge IP is configured, point the
            # identifier at our edge so the upstream reaches us (used in tests; in production
            # a wildcard A record already points at the edge).
            if settings.edge_public_ip and getattr(provider, "supports_a", False):
                provider.publish_a(domain, settings.edge_public_ip)
                published_a.append(domain)
            work.append((challb, response))

        for challb, response in work:
            acme_client.answer_challenge(challb, response)

        deadline = datetime.datetime.now() + datetime.timedelta(
            seconds=settings.upstream_finalize_timeout
        )
        finalized = acme_client.finalize_order(orderr, deadline)
        return finalized.fullchain_pem
    finally:
        edge.stop()
        for domain in published_a:
            try:
                provider.remove_a(domain, settings.edge_public_ip)
            except Exception:  # noqa: BLE001 - cleanup is best-effort
                logger.warning("Failed to clean up A record for %s", domain, exc_info=True)


def revoke_certificate(cert_pem: str, reason: int | None = None) -> None:
    """Revoke a certificate at the upstream CA (best-effort; requires pyOpenSSL)."""
    settings = get_settings()
    acme_client, _ = build_client(settings)
    try:
        import josepy
        from OpenSSL import crypto
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Certificate revocation requires pyOpenSSL") from exc

    x509 = crypto.load_certificate(crypto.FILETYPE_PEM, cert_pem.encode("ascii"))
    acme_client.revoke(josepy.ComparableX509(x509), reason or 0)
