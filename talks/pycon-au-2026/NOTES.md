# Run sheet — 5:00, hard stop

Sixteen slides in the talk, plus three appendix slides you don't present. The violet slides
(title, the "that's the core" divider, the close) are breathing room. Slide 7, the
architecture, is the only one that deserves a full thirty seconds. If you're behind at
slide 14, cut it — the row that matters is the last one.

| # | Slide | In at | Beat |
| --- | --- | --- | --- |
| 1 | acme-lan | 0:00 | Title. Real certs, unreachable hosts. |
| 2 | One name, two worlds | 0:12 | Split-horizon DNS. The CA can't reach the box. |
| 3 | How ACME actually works | 0:32 | http-01 / tls-alpn-01 / dns-01. Only one of them survives. |
| 4 | The one prerequisite | 0:54 | Public names only — and split horizon is easy now. |
| 5 | The three usual answers | 1:12 | Tokens everywhere / private CA / self-signed. Footnote promises the CNAME. |
| 6 | The whole idea | 1:32 | ACME server + ACME client. Stock clients, one line changes. |
| 7 | The architecture | 1:48 | **The big one.** Both conversations, and the DNS hop. |
| 8 | The one decision that matters | 2:18 | Forward the client's CSR. |
| 9 | Where the DNS credentials live | 2:38 | Three options. Pay off the footnote here. |
| 10 | That's the core | 3:08 | Divider. Six seconds, then move. |
| 11 | Things that never run ACME | 3:14 | Device push, two CSR modes, deploy plugins. |
| 12 | It comes with a dashboard | 3:36 | Screenshot. Don't read it out. |
| 13 | Live health, not a spreadsheet | 3:52 | Raw TLS handshake, not an HTTP request. |
| 14 | Should you use this? Maybe! | 4:08 | **Cut if you're behind** — but land the last row if you can. |
| 15 | The Python bits | 4:26 | FastAPI, certbot's acme lib, Pebble. |
| 16 | Try it | 4:42 | Repo, one docker run, thanks. |
| A1 | Appendix | — | Divider. Not presented. |
| A2 | Prior art I borrowed from | — | acme-dns and acme2certifier, for the hallway. |
| A3 | Two challenges, two directions | — | Downstream vs upstream, if anyone asks. |

## Script

**1 — acme-lan (0:00).** Five minutes, so I'm going to move. acme-lan is an internal ACME
server that hands out real, publicly-trusted certificates to hosts the internet has never
heard of. No relation to the anvil company — although both are elaborate schemes that mostly
work.

**2 — One name, two worlds (0:12).** `db.example.net` is a real name in a real public zone.
On the LAN it resolves to a private IP; from the internet there's nothing to reach. But the
CA doesn't need to reach the box — it needs proof you control the name.

**3 — How ACME actually works (0:32).** Which is the whole protocol, really. A CA will
certify any name you can prove you control, and there are three ways to prove it: serve a
token over HTTP on port 80, answer a special TLS handshake on 443, or publish a TXT record
at `_acme-challenge`. Your LAN host can never answer the first two from the internet. So:
dns-01.

**4 — The one prerequisite (0:54).** Non-negotiable: your internal names have to be public
names. No `.local`, no `.internal`, no `.lan` — a public CA won't certify a name nobody owns.
Good time to finally use that two-letter domain you've been hoarding. The good news is split
horizon stopped hurting: unbound and dnsmasq override just the names you host and pass the
rest of the zone straight through, so there's no second copy to keep in sync.

**5 — The three usual answers (1:12).** Put a DNS token on every host — a zone-wide
credential on a printer. Run your own CA — genuinely fine, until you're installing a root on
every laptop, phone and contractor, forever. Or self-sign and look away, which is the
industry standard. *(Footnote, out loud: yes, you can shrink that token by delegating
`_acme-challenge` — hold that thought.)*

**6 — The whole idea (1:32).** Be an ACME server on the inside and an ACME client on the
outside. RFC 8555 both directions, so certbot, acme.sh and the ACME client already built into
Proxmox need no plugin and no hook script — one line changes, the directory URL.

**7 — The architecture (1:48).** Client talks ACME to me over the LAN and proves control with
http-01 or tls-alpn-01. I turn around, open an order at the real CA for the same names, and
prove control with DNS-01 by writing a TXT into a zone I delegated for exactly this. The only
box on the LAN holding a DNS credential is this one.

**8 — The one decision that matters (2:18).** At finalize the client sends me its CSR. I
don't generate a key — I forward that same CSR upstream. So the certificate that comes back
matches a private key that never left the client. A proxy that made up its own keys would
just be a very expensive self-signed certificate.

**9 — Where the DNS credentials live (2:38).** Here's the payoff. Option one: zone
credentials on every host — the token rewrites everything, and rotating it means touching
every box. Option two: CNAME `_acme-challenge` to a zone of its own, so the token can only
write there — much smaller blast radius, but it's still on every box and still rotated
everywhere. Option three is this project: the same narrow token, in exactly one place.
Rotate it once, and every other box speaks plain ACME and holds nothing at all. Two axes at
once — what a leak can do, and how many places you have to fix.

**10 — That's the core (3:08).** That's the whole idea. Everything after this is scope creep
I'm happy about.

**11 — Things that never run ACME (3:14).** Register the box as a managed host and acme-lan
does issuance, install and renewal for it. Preferred mode: fetch a CSR the device generated
itself, sign it, push back only the certificate — nothing secret crosses the wire. Install
goes through deploy plugins; most network gear is driven over SSH, so a vendor plugin is one
class.

**12 — Dashboard (3:36).** Every certificate, every managed host, one page.

**13 — Live health (3:52).** The health column is a raw TLS handshake, not an HTTP request
that assumes 443 speaks HTTP. LDAPS, SMTPS, that one appliance on 8443 — expiry, chain trust,
SAN match, all of it honest.

**14 — Should you use this? Maybe! (4:08).** If your hosts reach the internet and can hold
DNS credentials, you don't need me. One reverse proxy in front of everything? Caddy. Happy to
run a private CA? step-ca is excellent. But if you want delegated DNS-01 with the clients you
already have, the alternative — as far as I know — is standing up acme-dns, and this is
likely easier than that.

**15 — The Python bits (4:26).** FastAPI and async SQLAlchemy, Alembic migrating on container
start. The upstream client is certbot's own `acme` library — the reference implementation is
right there on PyPI, so I didn't write an ACME client. End-to-end tests run against Pebble, a
real ACME CA that issues deliberately terrible certificates.

**16 — Try it (4:42).** One docker run, defaults to staging so you can't hurt yourself. MIT,
on GitHub. Thanks — no questions, lightning talk rules — but I'm in the hallway, and my
printer finally has a certificate nobody has to click through.

## Appendix (don't present)

**A2 — Prior art.** acme-dns: a tiny DNS server whose entire job is answering
`_acme-challenge`, and it expires its own records. Lovely idea — but it's an internet-facing
DNS server you run, and clients have to speak acme-dns, which most appliances never will.
acme-lan ships a provider for it anyway. acme2certifier: an ACME server that fronts other CAs
through `ca_handler` plugins — exactly where acme-lan's private-CA handler comes from, but it
doesn't do the split-horizon or device-push half.

**A3 — Two challenges, two directions.** The downstream challenge (proving to acme-lan, over
the LAN) and the upstream one (proving to the CA) are completely independent. Useful if
someone asks why tls-alpn-01 appears on one side and dns-01 on the other.
