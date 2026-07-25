# Operations & maintenance

Day-2 operations for a running **acme-lan**. For first-time install see
[DEPLOYMENT.md](DEPLOYMENT.md); for the key-handling model see [SECURITY.md](SECURITY.md).

- [Upgrades](#upgrades)
- [Backup & restore](#backup--restore)
- [The secret key](#the-secret-key)
- [Certificate lifecycle](#certificate-lifecycle)
- [Monitoring & health](#monitoring--health)
- [Database maintenance](#database-maintenance)
- [Rotating credentials](#rotating-credentials)
- [Logs & troubleshooting](#logs--troubleshooting)
- [Extending acme-lan](#extending-acme-lan)
- [Scaling & limitations](#scaling--limitations)

---

## Upgrades

acme-lan self-migrates: the container entrypoint runs schema migrations (Alembic) and
idempotent data migrations **before** serving, so upgrading is just bumping the image.

```bash
# Compose
docker compose pull
docker compose up -d
docker compose logs -f acme-lan     # look for "Applying schema migrations"
```

Recommended flow:

1. **Back up** `/app/data` and record your `ACME_LAN_SECRET_KEY` (see below).
2. Pin a specific tag (`ghcr.io/…/acme-lan:1.4.0`) rather than `latest` in production so
   upgrades are deliberate.
3. Pull + restart; watch the logs for the migration lines and a clean start.
4. Smoke-test: `curl -fsS <url>/healthz` and load the dashboard.

**Rollback:** migrations move the schema forward. Rolling the image *back* after a release
that changed the schema can leave the DB ahead of the older code. The safe rollback is:
restore the pre-upgrade `/app/data` backup **and** run the older image. So always snapshot
the volume before upgrading.

## Backup & restore

Everything acme-lan needs is in two places:

1. **The data volume** (`/app/data`) — the SQLite database (accounts, orders, issued certs,
   managed hosts, encrypted keys/credentials) and the public self-service cert.
2. **`ACME_LAN_SECRET_KEY`** — without it the encrypted contents of the database
   (device credentials, locally-generated keys, the upstream account key, the self-TLS key)
   **cannot be decrypted**. Store it in your password manager / secrets manager, separately
   from the volume backup.

Back up (SQLite, online-safe):

```bash
docker compose exec acme-lan sqlite3 /app/data/acme_lan.db ".backup '/app/data/backup.db'"
docker cp acme-lan:/app/data/backup.db ./acme-lan-$(date +%F).db
# or simply snapshot the whole named volume while stopped:
docker compose down && docker run --rm -v acme-lan-data:/data -v "$PWD":/out alpine \
  tar czf /out/acme-lan-data-$(date +%F).tgz -C /data . && docker compose up -d
```

Restore: stop acme-lan, replace the volume contents with the backup, ensure the **same**
`ACME_LAN_SECRET_KEY` is configured, start. Migrations bring the schema current on boot.

> If you use remote storage (`ACME_LAN_CERT_STORE_BACKEND=azure_keyvault|vault` or remote
> credential providers), those secrets live in Key Vault / Vault and are backed up there,
> not in the volume.

## The secret key

`ACME_LAN_SECRET_KEY` (Fernet) encrypts all at-rest secrets. Treat it like a root credential.

- **Losing it** makes encrypted DB contents unrecoverable — you'd re-enter device
  credentials and re-issue the upstream-account/self-TLS keys (new upstream account, new
  self cert). Issued host certs remain valid until they expire.
- **Rotating it** (there is no automatic re-encrypt yet): the practical path is to re-enter
  device credentials and let the upstream-account and self-TLS keys regenerate. If you need
  a bulk re-encrypt, add a data migration (see [Extending](#extending-acme-lan)) that reads
  with the old key and writes with the new one.

## Certificate lifecycle

- **Internal ACME clients** (certbot/acme.sh) renew themselves on their own schedule — they
  just re-run against acme-lan. acme-lan tracks every issuance (renewals are new rows).
- **Managed hosts** are renewed by acme-lan's scheduler when
  `ACME_LAN_AUTO_RENEW_ENABLED=true`: hosts whose latest cert expires within
  `ACME_LAN_RENEW_BEFORE_DAYS` (default 30) are re-issued and redeployed every
  `ACME_LAN_RENEW_CHECK_INTERVAL_SECONDS`. Force one now: `POST /api/hosts/{id}/renew`.
- **Self-service TLS cert** is refreshed by its own loop every
  `ACME_LAN_SELF_CERT_REFRESH_INTERVAL_SECONDS`; the new key/cert are picked up on the next
  restart (uvicorn loads TLS at startup).
- **Retiring a cert:** mark one "no longer required" so it stops raising expiry warnings:
  `POST /api/certificates/{id}/retire` (and `/unretire` to undo).

## Monitoring & health

- **Liveness:** `GET /healthz`.
- **Dashboard:** live TLS health for every cert (expiry, days left, chain trust, SAN match),
  computed by a raw-TLS probe — works for LDAPS/SMTPS/etc., not just HTTPS.
- **Ad-hoc probe:** `POST /api/health/probe {"host","port","server_name"}`.
- **Expiring soon:** `GET /api/certificates/expiring`.
- **Notifications:** email (Postmark) + webhook fire for certs within
  `ACME_LAN_EXPIRY_WARN_DAYS`; verify wiring with `POST /api/notifications/test` and list
  active channels with `GET /api/notifications/channels`.

## Database maintenance

SQLite is fine for homelab scale and needs little care. Housekeeping helpers live in
`acme_lan.maintenance` (`purge_expired_nonces`, `purge_expired_orders`); nonces are
single-use so they are largely self-limiting. To run GC on demand:

```bash
docker compose exec acme-lan python -c "
import asyncio
from acme_lan.db import session_scope
from acme_lan.maintenance import purge_expired_nonces, purge_expired_orders
from acme_lan.config import get_settings
async def main():
    async with session_scope() as s:
        n = await purge_expired_nonces(s, get_settings().nonce_max_age_seconds)
        o = await purge_expired_orders(s)
        print('purged nonces=%d orders=%d' % (n, o))
asyncio.run(main())
"
```

Occasionally reclaim space with `sqlite3 /app/data/acme_lan.db 'VACUUM;'` (while stopped).

## Rotating credentials

- **DNS provider token** (e.g. Cloudflare): update `ACME_LAN_CLOUDFLARE_API_TOKEN` and
  restart. No data migration needed.
- **Upstream account:** the account key is stored encrypted and reused. To force a fresh
  upstream account, change `ACME_LAN_UPSTREAM_ACCOUNT_KEY_PATH` (used only as a storage
  *name* now) — a new key/account is created on next use.
- **Device credentials:** update via `POST /api/credentials` (local) or rotate the secret in
  Key Vault / Vault (remote — nothing to change in acme-lan; it fetches at deploy time).
- **EAB / DigiCert profile creds:** `PATCH /api/acme-profiles/{name}` with new `eab_kid` /
  `eab_hmac_key`.
- **Admin token:** update `ACME_LAN_ADMIN_TOKEN` and restart.

## Logs & troubleshooting

Logs go to stdout (`docker compose logs -f acme-lan`). Common issues:

| Symptom | Likely cause / fix |
| --- | --- |
| Rate-limit / "too many certificates" from the CA | You're on production LE; test against **staging** first (`ACME_LAN_UPSTREAM_DIRECTORY_URL`). |
| Upstream DNS-01 fails | DNS token lacks `Zone.DNS:Edit`, wrong zone, or slow propagation — raise `ACME_LAN_DNS_PROPAGATION_SECONDS`. |
| Downstream HTTP-01 fails | acme-lan can't reach `http://<name>/.well-known/...`; the LAN name must resolve to the client and be reachable on port 80. |
| Self-TLS didn't start (stays HTTP) | `ACME_LAN_SELF_CERT_ENABLED=true` needs `ACME_LAN_SECRET_KEY` and a resolvable `ACME_LAN_SERVICE_DOMAIN`; check logs. |
| "wrote the service key to a 0600 temp file" warning | Running where `memfd_create` is unavailable (non-Linux); functionally fine, see [SECURITY.md](SECURITY.md). |
| `verify_ssl`/TLS errors against upstream | Only set `ACME_LAN_UPSTREAM_VERIFY_SSL=false` for test CAs (Pebble), never production. |
| Migration failed on startup | Check the log; restore the pre-upgrade backup and pin the previous image if needed. |
| Azure/Vault backend errors | Install the extra (`pip install .[storage]`) — already included in the published image — and verify provider settings/credentials. |

## Extending acme-lan

All extension points use small registries:

- **DNS provider:** add a class in `src/acme_lan/dns/` and wire it in `dns/factory.py`.
- **Deploy plugin:** subclass `DeployPlugin` and `deploy.factory.register_plugin(MyPlugin)`.
- **CA handler (private CA):** subclass `CaHandler` and `ca.factory.register_ca_handler(...)`.
- **Secret provider:** add to `secrets/factory.py` (mirror `certstore`).
- **Schema migration:** `uv run alembic revision --autogenerate -m "add X"`, review the
  generated file under `migrations/versions/`, commit. It applies automatically on next
  startup.
- **Data migration:** append `(stable_id, callable)` to `DATA_MIGRATIONS` in
  `src/acme_lan/migrations_data.py`; it runs once, after the schema upgrade.

Run the test suite after changes: `uv run pytest -q` (CI does the same on every push).

## Scaling & limitations

acme-lan is designed as a **single instance** for a LAN:

- SQLite and the in-process background loops (auto-renew, notifier, self-cert) assume one
  running process — do not run multiple replicas against the same database.
- The self-service TLS key is materialized per process; TLS config is loaded at startup, so
  a renewed self-cert is applied on the next restart.
- For larger deployments, point `ACME_LAN_DATABASE_URL` at PostgreSQL
  (`postgresql+asyncpg://…`; migrations handle the sync driver automatically) and run behind
  a reverse proxy — but keep a single app instance for the schedulers.
