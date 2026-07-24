# acme-lan Roadmap

The long-term vision, so the bigger plan isn't lost while we build incrementally.
Phase 1 is implemented; Phases 2–4 are planned.

## Phase 1 — Core ACME proxy + e2e  ✅ (this milestone)

- RFC 8555 server endpoints for standard clients (certbot / acme.sh): directory, newNonce,
  newAccount, newOrder, authorizations, challenges (http-01 downstream validation),
  finalize, certificate download, revoke.
- Upstream ACME client (certbot's `acme` library) that issues from a real public CA via
  **DNS-01**, forwarding the internal client's CSR so the cert matches the client's key.
- Pluggable DNS providers: **Cloudflare** (real) + **pebble-challtestsrv** (tests).
- SQLite storage; single FastAPI app.
- End-to-end test: a real ACME client → acme-lan → **Pebble** upstream → valid chain.

## Phase 2 — Web dashboard + realtime TLS health

- REST API over the same DB: list orders/certificates, issuance & renewal history, detail.
- **Realtime TLS health probe**: when the dashboard is viewed, open a raw TLS connection to
  each managed endpoint's configured `host:port` — *not* assuming HTTPS, so it works for
  LDAPS / SMTPS / etc. — read the leaf certificate and report expiry, chain validity, SAN
  match, and days remaining (a `check_ssl_cert`-style probe via `ssl` + `cryptography`).
- **Vue 3 + Vite + TypeScript + TailwindCSS** SPA: certificate table with health badges,
  an issue/renew timeline, and a manual "re-check now" action.
- Single-tenant homelab auth: one admin, session-cookie login (or trusted reverse-proxy
  header). No multi-user roles.

## Phase 3 — Managed hosts + device push (certgrinder-style automation)

- **Host registry**: register endpoints that can't run an ACME client (ESXi, iDRAC/iLO,
  printers, switches), each with its domain(s), target `host:port`, and a deploy plugin.
- **Credential repo**: encrypted store (Fernet/age, key from env/KMS) for the
  username/password or SSH keys used to log in and install certificates.
- **Deploy plugin interface** — `deploy(host, cert, key, chain)` implementations:
  - `ssh` — scp the cert + run a reload command,
  - `esxi` — upload to `/etc/vmware/ssl` and restart `hostd`,
  - a template for adding vendor-specific plugins (printers via IPP, etc.).
- **Auto-renew scheduler**: renew before expiry via the Phase-1 proxy, invoke the deploy
  plugin, then re-probe health to confirm the new cert is actually live on the device.

## Phase 4 — Hardening / ops

- Alternative upstream fulfilment: **edge HTTP-01 / TLS-ALPN-01** (server listens on the
  public edge IP with wildcard DNS pointing at it) as a pluggable option to DNS-01.
- More DNS providers: **RFC 2136** (nsupdate/TSIG) and **acme-dns** delegation.
- Downstream `dns-01` and `tls-alpn-01` challenge validation (enables wildcards).
- Order/nonce garbage collection, structured logging + metrics, container image + compose
  for deployment, and backup/restore of the DB and credential store.
