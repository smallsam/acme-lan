"""Build a configured upstream ACME client using certbot's ``acme`` library.

This is the same protocol library certbot uses, so we speak real RFC 8555 to Let's
Encrypt / ZeroSSL / Pebble. The account key is generated once and persisted so we keep a
single stable upstream account across restarts.
"""

from __future__ import annotations

import josepy
from acme import client, messages

from ..config import Settings
from ..keystore import load_or_create_account_key


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
    # The path setting is now used only as a stable storage name; the key is kept encrypted
    # (or in memory), never written to disk in the clear.
    account_key_name = account_key_path or settings.upstream_account_key_path or "default"
    account_email = account_email if account_email is not None else settings.upstream_account_email

    account_key = load_or_create_account_key(account_key_name)
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
