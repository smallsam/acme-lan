# Run sheet — 5:00, hard stop

Twenty slides. The two big statement slides (`thisisunsafe`, "It's always DNS") are
breathing room — land the line, move on. Slide 5 (architecture) is the only one that
deserves a full thirty seconds. If you're behind at slide 17, cut the alternatives table.

| # | Slide | In at | Beat |
| --- | --- | --- | --- |
| 1 | acme-lan | 0:00 | Title. Real certs, unreachable hosts. |
| 2 | thisisunsafe | 0:12 | The problem, in one string everyone recognises. |
| 3 | One name, two worlds | 0:22 | Split-horizon DNS. The CA doesn't need to reach the box. |
| 4 | The three usual answers | 0:38 | Tokens everywhere / private CA / self-signed. |
| 5 | Why I built it anyway | 0:54 | 0 appliances, 1 credential holder, 90 days. |
| 6 | The whole idea | 1:06 | ACME server + ACME client. One line changes on the client. |
| 7 | The architecture | 1:16 | **The big one.** Both conversations, and the DNS hop. |
| 8 | The one decision that matters | 1:44 | Forward the client's CSR. |
| 9 | Two challenges, two directions | 2:00 | http-01 / tls-alpn-01 down, dns-01 / edge http-01 up. |
| 10 | It's always DNS | 2:14 | Laugh line, then the sting: one box, whole zone. |
| 11 | Chaining to acme-dns | 2:22 | Register, one CNAME, never touch DNS again. |
| 12 | Blast radius | 2:46 | Why the CNAME is worth it. |
| 13 | For things that never run ACME | 2:58 | Device push, two CSR modes, deploy plugins. |
| 14 | It comes with a dashboard | 3:16 | Screenshot. Don't read it out. |
| 15 | Live health, not a spreadsheet | 3:28 | Raw TLS handshake, not an HTTP request. |
| 16 | Adding a device | 3:40 | PluginFields render the form. |
| 17 | Should you use this? | 3:50 | **Cut this slide if you're behind.** |
| 18 | The Python bits | 4:08 | FastAPI, certbot's acme lib, Pebble. |
| 19 | Three things I'd tell past me | 4:22 | Forward the CSR / staging / no plaintext keys. |
| 20 | Try it | 4:36 | Repo, one docker run, thanks. |

## Script

**1 — acme-lan (0:00).** Five minutes, so I'm going to move. acme-lan is an internal ACME
server that hands out real, publicly-trusted certificates to hosts the internet has never
heard of. No relation to the anvil company — although both are elaborate schemes that
mostly work.

**2 — thisisunsafe (0:12).** Everyone here knows this string. You type it into a Chrome
interstitial and it clicks through. I know it by muscle memory. That's the bug.

**3 — One name, two worlds (0:22).** `db.example.net` is a real name in a real public zone.
On the LAN it resolves to a private IP; from the internet there's nothing to reach. But
Let's Encrypt doesn't need to reach the box — it needs proof you control the name. That
proof is a TXT record, which means somebody has to hold DNS credentials.

**4 — The three usual answers (0:38).** Put a DNS token on every host — that's a zone-wide
credential on a printer. Run your own CA — genuinely fine, until you're installing a root
on every laptop, phone and contractor, forever. Or self-sign and look away, which is the
industry standard, and which is slide two.

**5 — Why I built it anyway (0:54).** Zero of my appliances will ever run certbot. One
machine should hold the DNS credential. And ninety days comes around whether I'm paying
attention or not.

**6 — The whole idea (1:06).** Be an ACME server on the inside and an ACME client on the
outside. RFC 8555 both directions, so certbot and acme.sh need no plugin and no patch —
one line changes, the directory URL.

**7 — The architecture (1:16).** Client talks ACME to me over the LAN and proves control
with http-01 or tls-alpn-01. I turn around, open an order at the real CA for the same
names, and prove control with DNS-01 by publishing a TXT record. The only box on the LAN
holding a DNS credential is this one.

**8 — The one decision that matters (1:44).** At finalize the client sends me its CSR. I
don't generate a key — I forward that same CSR upstream. So the certificate that comes
back matches a private key that never left the client. A proxy that made up its own keys
would just be a very expensive self-signed certificate.

**9 — Two challenges, two directions (2:00).** Downstream: http-01 if the box has a web
server, tls-alpn-01 if it doesn't — the challenge rides in the TLS handshake itself.
Upstream: DNS-01 by default, so nothing needs to be publicly reachable; or edge http-01 if
you actually have a public IP and hate waiting for DNS.

**10 — It's always DNS (2:14).** The protocol designers agreed with you so completely they
made a whole challenge type out of it. But now one box holds a token that can rewrite your
entire zone. Better than thirty-seven copies of it. Still not good.

**11 — Chaining to acme-dns (2:22).** Register once with acme-dns, get a random subdomain.
Add one CNAME per name — a one-time edit to your real zone. From then on acme-lan just
POSTs the TXT value to `/update`, and removal is a no-op because acme-dns expires them
itself. It's a DNS server with exactly one opinion, and that opinion is "yes, that TXT
record is mine".

**12 — Blast radius (2:46).** A leaked zone token rewrites anything — MX, SPF, your mail.
Leaked acme-dns credentials set one TXT record on one delegated subdomain: worst case,
certificates for the names you delegated. Bad, but bounded. Same protocol, one CNAME of
separation.

**13 — Things that never run ACME (2:58).** Register the box as a managed host and acme-lan
does issuance, install and renewal for it. Preferred mode: fetch a CSR the device generated
itself, sign it, push back only the certificate — nothing secret crosses the wire. Install
goes through deploy plugins; most network gear is driven over SSH, so a vendor plugin is
one class.

**14 — Dashboard (3:16).** Every certificate, every managed host, one page.

**15 — Live health (3:28).** The health column is a raw TLS handshake, not an HTTP request
that assumes 443 speaks HTTP. LDAPS, SMTPS, that one appliance on 8443 — expiry, chain
trust, SAN match, all of it honest.

**16 — Adding a device (3:40).** Plugins declare their config as PluginFields and the
dashboard renders exactly the right form, changing as you switch plugin or CSR mode. Write
a plugin, get a UI.

**17 — Should you use this? (3:50).** Probably not. If your hosts reach the internet and
can hold DNS credentials, use certbot with a DNS plugin and go and enjoy the hallway track.
Happy to run a private CA? step-ca is excellent. Only need delegated DNS-01? acme-dns on
its own is the good part of this talk. One reverse proxy in front of everything? Caddy.
It's the last row that's this: appliances that can't run ACME, split-horizon names, one
place to see all of it.

**18 — The Python bits (4:08).** FastAPI and async SQLAlchemy, Alembic migrating on
container start. The upstream client is certbot's own `acme` library — the reference
implementation is right there on PyPI, so I didn't write an ACME client. End-to-end tests
run against Pebble, a real ACME CA that issues deliberately terrible certificates.

**19 — Three things I'd tell past me (4:22).** Forward the CSR — everything else falls out
of that. Stay on staging longer than you think; rate limits are a patient teacher. And no
plaintext private keys at rest, ever, including the ones you generated yourself.

**20 — Try it (4:36).** One docker run, defaults to staging so you can't hurt yourself.
MIT, on GitHub. Thanks — no questions, lightning talk rules — but I'm in the hallway, and
my printer finally has a certificate nobody has to click through.
