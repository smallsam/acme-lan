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

## Phase 2 — Web dashboard + realtime TLS health  ✅

- REST API over the same DB (`/api/...`): certificate list + detail, order stats.
- **Realtime TLS health probe** (`acme_lan/health.py`): opens a raw TLS connection to a
  `host:port` — *not* assuming HTTPS, so it works for LDAPS / SMTPS / etc. — reads the leaf
  certificate and reports expiry, days remaining, chain trust, SAN match, and self-signed
  status (a `check_ssl_cert`-style probe via `ssl` + `cryptography`). Exposed as
  `POST /api/health/probe` (ad hoc) and `GET /api/certificates/{id}/health`.
- **Vue 3 + Vite + TypeScript + TailwindCSS** SPA (`src/acme_lan/web`): certificate table
  with live health badges, a "re-check now" action, and an ad-hoc TLS probe form.
- Single-tenant homelab auth: an optional admin bearer token (`ACME_LAN_ADMIN_TOKEN`) that
  gates the management API only; the ACME endpoints are never gated.

## Phase 3 — Managed hosts + device push (certgrinder-style automation)  ✅

- **Host registry** (`ManagedHost`): endpoints that can't run an ACME client (ESXi, iDRAC,
  printers, switches), each with domain(s), target address/port, deploy plugin and config.
  Full CRUD via `/api/hosts`.
- **Credential repo** (`acme_lan/credentials.py`, `StoredCredential`): Fernet-encrypted
  store (key from `ACME_LAN_SECRET_KEY`) for device passwords / SSH keys. Secrets are
  write-only over the API and only decrypted to perform a deploy.
- **Deploy plugin interface** (`acme_lan/deploy/`): `deploy(ctx)` with a `local` plugin
  (write files + reload command) and an `ssh` plugin (SFTP upload + reload over paramiko);
  a factory/registry makes adding vendor plugins straightforward.
- **Issue-and-deploy** (`acme_lan/hosts.py`): for a managed host, acme-lan generates the
  key + CSR, issues via the Phase-1 upstream proxy (DNS-01), pushes cert + key to the
  device, and records the result. `hosts_needing_renewal()` selects certs expiring within
  `ACME_LAN_RENEW_BEFORE_DAYS`; `POST /api/hosts/{id}/renew` runs the whole flow.

Deferred to Phase 4: a background scheduler that periodically renews due hosts (the
selection + one-shot renew/deploy are implemented and API-triggerable today).

## Phase 4 — Hardening / ops  ✅ (partial; remaining items noted)

- **Edge HTTP-01 upstream** (`ACME_LAN_UPSTREAM_CHALLENGE=http-01`): the alternative to
  DNS-01. acme-lan answers the upstream's http-01 from an edge HTTP responder
  (`acme_lan/upstream/edge.py`); with wildcard DNS pointing at the edge IP this is faster
  than DNS propagation. Covered by a Pebble e2e.
- **acme-dns** DNS provider (`acme_lan/dns/acmedns.py`), pluggable alongside Cloudflare.
- **Auto-renew scheduler** (`acme_lan/scheduler.py`): a background loop
  (`ACME_LAN_AUTO_RENEW_ENABLED`) that renews due managed hosts on an interval.
- **Garbage collection** (`acme_lan/maintenance.py`): purge stale nonces and expired
  non-valid orders.
- **Container image** (`Dockerfile`, runs the pre-built dashboard) and structured logging.

Still open (future work): TLS-ALPN-01 upstream, RFC 2136 (nsupdate/TSIG) provider,
downstream `dns-01` / `tls-alpn-01` validation for wildcards, Prometheus metrics, and
DB/credential backup-restore tooling.
