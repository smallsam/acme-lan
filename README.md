# acme-lan

An **internal ACME server** for split-horizon LANs. Point standard ACME clients
(`certbot`, `acme.sh`) at it and they receive **real, publicly-trusted certificates** —
even for hosts that are only reachable on your LAN and never exposed to the internet.

acme-lan speaks RFC 8555 to your internal clients, then fulfils each request by acting as
an ACME *client* to a real public CA (Let's Encrypt / ZeroSSL), proving control with a
**DNS-01** challenge against your public zone. Only this server holds the DNS credentials.

```
 internal client            acme-lan (this server)              upstream CA (Let's Encrypt)
 certbot / acme.sh  ──ACME──▶  ACME server  ─────ACME client────▶  real issuance
                               │  proves LAN control (http-01)
                               └▶ publishes _acme-challenge TXT ──▶ upstream DNS-01 validates
```

Think of it as a mashup of [certgrinder](https://github.com/tykling/certgrinder) (central
host does the ACME heavy lifting) and
[acme2certifier](https://github.com/grindsa/acme2certifier) (an ACME front-end proxying to
a CA backend) — but the backend is a real public CA reached via DNS-01, and clients talk
**standard ACME** so nothing on them needs to change.

## Why

Split-horizon DNS means `db.example.net` resolves to `192.168.3.5` on the LAN while
`example.net` is a real public zone. Internal hosts want real certs but:

- they aren't publicly reachable, so plain HTTP-01 to Let's Encrypt won't work, and
- they shouldn't each hold DNS-provider API credentials.

acme-lan solves both: clients do a normal ACME exchange with a server on the LAN, and the
one server that *does* hold DNS credentials performs the real DNS-01 issuance upstream.

## Status

Phases 1 and 2 are implemented; see [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full plan.

**Phase 1 — core ACME proxy:**

- RFC 8555 server: directory, newNonce, newAccount, newOrder, authorizations, challenges
  (http-01 downstream validation), finalize, certificate download, revoke.
- Upstream client (certbot's `acme` library) that issues via **DNS-01**.
- DNS providers: **Cloudflare** (real) and **pebble-challtestsrv** (tests). Pluggable.
- SQLite storage; single self-contained FastAPI app.
- End-to-end test: real ACME client → acme-lan → **Pebble** upstream → a valid chain.

**Phase 2 — web dashboard + realtime TLS health:**

- Management REST API (`/api/...`): certificate list/detail, order stats.
- Realtime TLS health probe (raw TLS, works for LDAPS/SMTPS/etc.) via
  `POST /api/health/probe` and `GET /api/certificates/{id}/health`.
- Vue 3 + Vite + TailwindCSS dashboard (`src/acme_lan/web`) with live health badges and an
  ad-hoc probe form, served by the app when built.
- Optional admin bearer token (`ACME_LAN_ADMIN_TOKEN`) gating the management API only.

**Phase 3 — managed hosts + device push:**

- Host registry + Fernet-encrypted credential store for devices that can't run ACME.
- Deploy plugins (`local`, `ssh`) with a registry for adding more.
- For a managed host, acme-lan generates the key + CSR, issues via the upstream proxy, and
  pushes cert + key to the device (`POST /api/hosts/{id}/renew`); renewal selection picks
  hosts expiring within `ACME_LAN_RENEW_BEFORE_DAYS`.

**Phase 4 — hardening / ops:**

- Edge **HTTP-01 upstream** path (`ACME_LAN_UPSTREAM_CHALLENGE=http-01`) as a pluggable
  alternative to DNS-01, plus an **acme-dns** DNS provider.
- Background **auto-renew scheduler** (`ACME_LAN_AUTO_RENEW_ENABLED`) and nonce/order GC.
- `Dockerfile` (serves the pre-built dashboard) and structured logging.

**Certificate lifecycle & delivery:**

- Every issued cert is tracked (renewals are new rows); the dashboard shows days-to-expiry
  and warns; **retire** a cert (`POST /api/certificates/{id}/retire`) so it stops warning.
- **Expiry notifications** over pluggable channels: **Postmark** email + generic webhook.
- Pluggable **key/cert storage**: local (encrypted in DB), **Azure Key Vault**, **Vault**.

**Device push — two modes:**

- `csr_source="device"` (preferred): sign a CSR fetched from the device; the private key
  never touches acme-lan. `csr_source="local"`: acme-lan generates the key (UI warns).

**Multiple ACME listeners:**

- Named profiles under `/acme/p/<name>/` each proxy to a different upstream — an
  EAB-authenticated ACME CA (e.g. DigiCert) or a **private CA** via an acme2certifier-style
  `ca_handler` (ships a `local_ca` that signs CSRs, for WiFi/private-CA certs).

**Self TLS:** with `ACME_LAN_SERVICE_DOMAIN` + `SELF_CERT_ENABLED`, acme-lan obtains and
renews its **own** certificate and serves the admin UI / ACME endpoints over trusted HTTPS
— eliminating cert warnings across the LAN.

## Quickstart

```bash
uv sync --extra dev

# Configure (see .env.example for all options)
cp .env.example .env
$EDITOR .env      # set upstream + Cloudflare token

uv run acme-lan   # serves http://localhost:8000/acme/directory
```

Point a client at it:

```bash
acme.sh --issue -d db.example.net --server http://acme-lan.lan:8000/acme/directory ...
# or
certbot certonly --server http://acme-lan.lan:8000/acme/directory ...
```

## How a request flows

1. Client does `newAccount` / `newOrder` for `db.example.net`.
2. acme-lan returns an **http-01** challenge; the client serves the token and acme-lan
   validates it by fetching it over the LAN (defence-in-depth / protocol compliance).
3. At **finalize** the client submits its CSR. acme-lan opens an order at the upstream CA
   for the same names, publishes the `_acme-challenge` TXT record via the DNS provider,
   answers the upstream **DNS-01** challenge, and finalizes upstream **with the client's
   own CSR** — so the issued cert matches the client's private key.
4. acme-lan returns the upstream-issued chain to the client.

## Testing

```bash
uv run pytest -q            # unit + provider tests
uv run pytest tests/e2e -q  # end-to-end (needs a Pebble upstream, see below)
```

The e2e suite runs a real ACME client against acme-lan with **Pebble** (Let's Encrypt's
reference test CA) + **pebble-challtestsrv** as the upstream, and asserts a valid chain is
returned whose leaf key matches the client's CSR.

The `pebble` fixture prefers locally-built Go binaries and skips cleanly if they're absent:

```bash
go install github.com/letsencrypt/pebble/v2/cmd/pebble@latest
go install github.com/letsencrypt/pebble/v2/cmd/pebble-challtestsrv@latest
# binaries land in $(go env GOPATH)/bin — put that on PATH, or point the fixture at them
# with PEBBLE_BIN / CHALLTESTSRV_BIN.
```

A Docker Compose alternative for the same two services is provided in
[`docker-compose.test.yml`](docker-compose.test.yml).

## Deployment & development

- **Docker:** the `Dockerfile` builds a self-contained image (the dashboard is pre-built).
  Tagging a release `vX.Y.Z` triggers [`.github/workflows/release.yml`](.github/workflows/release.yml)
  to build a multi-arch image and push it to Docker Hub (set `DOCKERHUB_USERNAME` /
  `DOCKERHUB_TOKEN` secrets). The container entrypoint **auto-migrates** the database
  (Alembic schema + idempotent data migrations) before serving, so upgrading the image
  upgrades an existing volume in place.
- **Dev container:** open in a [devcontainer](.devcontainer/devcontainer.json) (Python +
  Node + Go + Docker); the post-create installs all deps and builds the Pebble test
  binaries so `uv run pytest -q` works immediately.
- **CI:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs ruff + the full test
  suite (including the Pebble-backed e2e tests) on every push/PR.

## Security (key handling)

No private key material is stored in the database or on disk in the clear (the one opt-in
exception is device-push local key generation). See [`docs/SECURITY.md`](docs/SECURITY.md).
Device-push credentials and issued cert/key bundles can live in **Azure Key Vault** or
**HashiCorp Vault** instead of the local (encrypted) database.

## Configuration

All settings use the `ACME_LAN_` env prefix; see [`.env.example`](.env.example).

## License

MIT
