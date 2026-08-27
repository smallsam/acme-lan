# Run sheet — 5:00, hard stop

Twenty-one slides. The violet slides (`thisisunsafe`, "It's always DNS", the title and the
close) are breathing room — land the line and move on. Slide 8, the architecture, is the
only one that deserves a full twenty-five seconds. If you're behind at slide 18, cut it.

| # | Slide | In at | Beat |
| --- | --- | --- | --- |
| 1 | acme-lan | 0:00 | Title. Real certs, unreachable hosts. |
| 2 | thisisunsafe | 0:12 | The problem, in one string everyone recognises. |
| 3 | One name, two worlds | 0:20 | Split-horizon DNS. The CA doesn't need to reach the box. |
| 4 | The one prerequisite | 0:36 | Public names only — and split horizon is easy now. |
| 5 | The three usual answers | 0:50 | Tokens everywhere / private CA / self-signed. |
| 6 | Why I built it anyway | 1:04 | 0 appliances, 1 credential holder, 90 days. |
| 7 | The whole idea | 1:14 | ACME server + ACME client. Stock clients, one line changes. |
| 8 | The architecture | 1:24 | **The big one.** Both conversations, and the DNS hop. |
| 9 | The one decision that matters | 1:50 | Forward the client's CSR. |
| 10 | Two challenges, two directions | 2:04 | http-01 / tls-alpn-01 down, dns-01 / edge http-01 up. |
| 11 | It's always DNS | 2:18 | Laugh line, then the sting: one box, whole zone. |
| 12 | Delegate the challenge | 2:26 | The CNAME. This is the real blast-radius fix. |
| 13 | Where acme-dns fits | 2:50 | Supported, neat, and not an upgrade over the CNAME. |
| 14 | Things that never run ACME | 3:06 | Device push, two CSR modes, deploy plugins. |
| 15 | It comes with a dashboard | 3:24 | Screenshot. Don't read it out. |
| 16 | Live health, not a spreadsheet | 3:34 | Raw TLS handshake, not an HTTP request. |
| 17 | Adding a device | 3:46 | PluginFields render the form. |
| 18 | Should you use this? | 3:56 | **Cut this slide if you're behind.** |
| 19 | The Python bits | 4:12 | FastAPI, certbot's acme lib, Pebble. |
| 20 | Three things I'd tell past me | 4:24 | Forward the CSR / staging / no plaintext keys. |
| 21 | Try it | 4:38 | Repo, one docker run, thanks. |

## Script

**1 — acme-lan (0:00).** Five minutes, so I'm going to move. acme-lan is an internal ACME
server that hands out real, publicly-trusted certificates to hosts the internet has never
heard of. No relation to the anvil company — although both are elaborate schemes that
mostly work.

**2 — thisisunsafe (0:12).** Everyone here knows this string. You type it into a Chrome
interstitial and it clicks through. I know it by muscle memory. That's the bug.

**3 — One name, two worlds (0:20).** `db.example.net` is a real name in a real public zone.
On the LAN it resolves to a private IP; from the internet there's nothing to reach. But
Let's Encrypt doesn't need to reach the box — it needs proof you control the name. That
proof is a TXT record, which means somebody has to hold DNS credentials.

**4 — The one prerequisite (0:36).** Non-negotiable: your internal names have to be public
names. No `.local`, no `.internal`, no `.lan` — a public CA won't certify a name nobody
owns. Good time to finally use that two-letter domain you've been hoarding. The good news
is split horizon stopped hurting: unbound and dnsmasq will override just the names you host
on the LAN and pass the rest of the zone straight through, so there's no second copy to keep
in sync.

**5 — The three usual answers (0:50).** Put a DNS token on every host — that's a zone-wide
credential on a printer. Run your own CA — genuinely fine, until you're installing a root on
every laptop, phone and contractor, forever. Or self-sign and look away, which is the
industry standard, and which is slide two.

**6 — Why I built it anyway (1:04).** Zero of my appliances will ever run certbot. One
machine should hold the DNS credential. And ninety days comes around whether I'm paying
attention or not.

**7 — The whole idea (1:14).** Be an ACME server on the inside and an ACME client on the
outside. RFC 8555 both directions, so certbot, acme.sh and the ACME client already built
into Proxmox need no plugin and no hook script — one line changes, the directory URL.

**8 — The architecture (1:24).** Client talks ACME to me over the LAN and proves control
with http-01 or tls-alpn-01. I turn around, open an order at the real CA for the same names,
and prove control with DNS-01 by writing a TXT record into a zone I delegated for exactly
this. The only box on the LAN holding a DNS credential is this one.

**9 — The one decision that matters (1:50).** At finalize the client sends me its CSR. I
don't generate a key — I forward that same CSR upstream. So the certificate that comes back
matches a private key that never left the client. A proxy that made up its own keys would
just be a very expensive self-signed certificate.

**10 — Two challenges, two directions (2:04).** Downstream: http-01 if the box has a web
server, tls-alpn-01 if it doesn't — the challenge rides in the TLS handshake itself.
Upstream: DNS-01 by default, so nothing needs to be publicly reachable; or edge http-01 if
you actually have a public IP and hate waiting for DNS.

**11 — It's always DNS (2:18).** The protocol designers agreed with you so completely they
made a whole challenge type out of it. But now one box holds a token that can rewrite your
entire zone. Better than thirty-seven copies of it — still worth scoping down.

**12 — Delegate the challenge, not the zone (2:26).** And you can, without any new software.
CNAME the `_acme-challenge` record for each name at a zone you delegate. Every CA follows
that CNAME — it's how DNS-01 was designed to be used. acme-lan then only needs a token that
can write in the delegated zone, and nothing at all in the zone that runs your mail. One
record per name, set once. That's the whole blast-radius story.

**13 — Where acme-dns fits (2:50).** Because someone always asks. acme-dns is purpose-built
for this: register once, one CNAME, POST each TXT to `/update`, and removal is a no-op
because it expires records itself. acme-lan ships a provider for it and it works. But be
honest — once you've delegated `_acme-challenge`, acme-dns gives you the same blast radius
in exchange for an internet-facing DNS server you now run forever, and on its own it needs
clients that speak acme-dns, which most appliances never will. It's an alternative
architecture, not an upgrade. Use it if you already run one.

**14 — Things that never run ACME (3:06).** Register the box as a managed host and acme-lan
does issuance, install and renewal for it. Preferred mode: fetch a CSR the device generated
itself, sign it, push back only the certificate — nothing secret crosses the wire. Install
goes through deploy plugins; most network gear is driven over SSH, so a vendor plugin is one
class.

**15 — Dashboard (3:24).** Every certificate, every managed host, one page.

**16 — Live health (3:34).** The health column is a raw TLS handshake, not an HTTP request
that assumes 443 speaks HTTP. LDAPS, SMTPS, that one appliance on 8443 — expiry, chain
trust, SAN match, all of it honest.

**17 — Adding a device (3:46).** Plugins declare their config as PluginFields and the
dashboard renders exactly the right form, changing as you switch plugin or CSR mode. Write a
plugin, get a UI.

**18 — Should you use this? (3:56).** Probably not. If your hosts reach the internet and can
hold DNS credentials, use certbot with a DNS plugin and go and enjoy the hallway track.
Happy to run a private CA? step-ca is excellent. Every client speaks acme-dns natively?
Run acme-dns on its own. One reverse proxy in front of everything? Caddy. It's the last row
that's this: appliances that can't run ACME, split-horizon names, one place to see all of it.

**19 — The Python bits (4:12).** FastAPI and async SQLAlchemy, Alembic migrating on
container start. The upstream client is certbot's own `acme` library — the reference
implementation is right there on PyPI, so I didn't write an ACME client. End-to-end tests run
against Pebble, a real ACME CA that issues deliberately terrible certificates.

**20 — Three things I'd tell past me (4:24).** Forward the CSR — everything else falls out of
that. Stay on staging longer than you think; rate limits are a patient teacher. And no
plaintext private keys at rest, ever, including the ones you generated yourself.

**21 — Try it (4:38).** One docker run, defaults to staging so you can't hurt yourself. MIT,
on GitHub. Thanks — no questions, lightning talk rules — but I'm in the hallway, and my
printer finally has a certificate nobody has to click through.
