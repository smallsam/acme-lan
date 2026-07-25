"""Build a configured upstream ACME client using certbot's ``acme`` library.

This is the same protocol library certbot uses, so we speak real RFC 8555 to Let's
Encrypt / ZeroSSL / Pebble. The account key is generated once and persisted so we keep a
single stable upstream account across restarts.
"""

from __future__ import annotations

import json
from pathlib import Path

import josepy
from acme import client, messages
from cryptography.hazmat.primitives.asymmetric import rsa

from ..config import Settings


def load_or_create_account_key(path_str: str) -> josepy.JWKRSA:
    """Load a persisted RSA account key, generating and saving one on first use."""
    path = Path(path_str)
    if path.exists():
        return josepy.JWKRSA.json_loads(path.read_text())
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    account_key = josepy.JWKRSA(key=josepy.ComparableRSAKey(rsa_key))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(account_key.to_json()))
    return account_key


def build_client(
    settings: Settings,
    *,
    directory_url: str | None = None,
    verify_ssl: bool | None = None,
    account_key_path: str | None = None,
    account_email: str | None = None,
    eab_kid: str = "",
    eab_hmac_key: str = "",
) -> tuple[client.ClientV2, josepy.JWKRSA]:
    """Return a registered :class:`acme.client.ClientV2` and its account key.

    Per-profile overrides let a single server proxy to several upstream CAs, including
    ones that require External Account Binding (EAB), e.g. DigiCert. Registering with an
    existing key is idempotent: the CA returns the existing account.
    """
    directory_url = directory_url or settings.upstream_directory_url
    verify_ssl = settings.upstream_verify_ssl if verify_ssl is None else verify_ssl
    account_key_path = account_key_path or settings.upstream_account_key_path
    account_email = account_email if account_email is not None else settings.upstream_account_email

    account_key = load_or_create_account_key(account_key_path)
    net = client.ClientNetwork(account_key, user_agent="acme-lan/0.1", verify_ssl=verify_ssl)
    directory = client.ClientV2.get_directory(directory_url, net)
    acme_client = client.ClientV2(directory, net=net)

    kwargs: dict = {"email": account_email or None, "terms_of_service_agreed": True}
    if eab_kid and eab_hmac_key:
        kwargs["external_account_binding"] = messages.ExternalAccountBinding.from_data(
            account_public_key=account_key.public_key(),
            kid=eab_kid,
            hmac_key=eab_hmac_key,
            directory=directory,
        )
    regr = acme_client.new_account(messages.NewRegistration.from_data(**kwargs))
    net.account = regr
    return acme_client, account_key
