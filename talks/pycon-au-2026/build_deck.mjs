// Build the PyCon AU 2026 lightning-talk deck for acme-lan.
//
//   npm install pptxgenjs && node talks/pycon-au-2026/build_deck.mjs
//
// Screenshots in ./img are captured from the current build with
// `uv run python tests/screenshot_server.py` + src/acme_lan/web/scripts/screenshot.mjs.
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const PptxGenJS = require('pptxgenjs')

const here = path.dirname(fileURLToPath(import.meta.url))
const IMG = (name) => path.join(here, 'img', name)
const OUT = path.join(here, 'acme-lan-pycon-au-2026.pptx')

// ---------------------------------------------------------------- palette --
const INK = '071A2F' // deep navy — dominant
const PANEL = '0E2A47' // card fill
const PANEL2 = '13375C' // lighter card fill
const BLUE = '4B8BBE' // python blue
const GOLD = 'FFD43B' // python yellow — the sharp accent
const GREEN = '3DDC97'
const CORAL = 'FF7A7A'
const TEXT = 'F2F7FC'
const MUTED = '93AEC9'
const WHITE = 'FFFFFF'

const SANS = 'Arial'
const MONO = 'Courier New'

const pres = new PptxGenJS()
pres.layout = 'LAYOUT_WIDE' // 13.333 x 7.5
pres.author = 'smallsam'
pres.title = 'acme-lan — PyCon AU 2026 lightning talk'

// ---------------------------------------------------------------- helpers --
// Shadows are deliberately off: on a dark deck they add nothing, and LibreOffice
// renders a visible halo above each shape when exporting to PDF.
const shadow = () => undefined

function newSlide(notes, bg = INK) {
  const s = pres.addSlide()
  s.background = { color: bg }
  if (notes) s.addNotes(notes)
  return s
}

/** Gold numbered badge — the deck's repeating motif. */
function badge(s, label) {
  s.addShape(pres.ShapeType.ellipse, { x: 0.62, y: 0.42, w: 0.62, h: 0.62, fill: { color: GOLD } })
  s.addText(String(label), {
    x: 0.62, y: 0.42, w: 0.62, h: 0.62, isTextBox: true, margin: 0,
    align: 'center', valign: 'middle', fontFace: SANS, fontSize: 20, bold: true, color: INK,
  })
}

function title(s, text, opts = {}) {
  s.addText(text, {
    x: 1.45, y: 0.36, w: 11.3, h: 0.78, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: opts.fontSize || 34, bold: true, color: opts.color || TEXT,
    align: 'left', valign: 'middle',
  })
}

/** Monospace kicker line, bottom-left. */
function kicker(s, text, color = BLUE) {
  s.addText(text, {
    x: 0.65, y: 6.72, w: 12.1, h: 0.4, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 12, color, align: 'left', valign: 'middle',
  })
}

/** A card: rounded panel + heading + body lines. */
function card(s, o) {
  s.addShape(pres.ShapeType.roundRect, {
    x: o.x, y: o.y, w: o.w, h: o.h, rectRadius: 0.09,
    fill: { color: o.fill || PANEL }, line: { color: o.border || PANEL2, width: 1 }, shadow: shadow(),
  })
  let cursor = o.y + 0.28
  if (o.eyebrow) {
    s.addText(o.eyebrow, {
      x: o.x + 0.32, y: cursor, w: o.w - 0.64, h: 0.28, isTextBox: true, margin: 0,
      fontFace: MONO, fontSize: 12, bold: true, color: o.eyebrowColor || GOLD, charSpacing: 1,
    })
    cursor += 0.36
  }
  if (o.head) {
    const hh = o.headH || 0.5
    s.addText(o.head, {
      x: o.x + 0.32, y: cursor, w: o.w - 0.64, h: hh, isTextBox: true, margin: 0,
      fontFace: o.headMono ? MONO : SANS, fontSize: o.headSize || 22, bold: true,
      color: o.headColor || TEXT, valign: 'top',
    })
    cursor += hh + 0.08
  }
  if (o.body) {
    s.addText(o.body, {
      x: o.x + 0.32, y: cursor, w: o.w - 0.64, h: o.y + o.h - cursor - 0.22, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: o.bodySize || 15, color: o.bodyColor || MUTED, valign: 'top', lineSpacingMultiple: 1.15,
    })
  }
}

/** Rounded white plate behind a light-UI screenshot. */
function shot(s, file, o) {
  s.addShape(pres.ShapeType.roundRect, {
    x: o.x - 0.09, y: o.y - 0.09, w: o.w + 0.18, h: o.h + 0.18, rectRadius: 0.07,
    fill: { color: WHITE }, line: { color: 'D6E2EE', width: 1 },
  })
  s.addImage({ path: IMG(file), x: o.x, y: o.y, w: o.w, h: o.h })
  if (o.caption) {
    s.addText(o.caption, {
      x: o.x, y: o.y + o.h + 0.16, w: o.w, h: 0.3, isTextBox: true, margin: 0,
      fontFace: MONO, fontSize: 11, color: MUTED,
    })
  }
}

// ============================================================== 1. title ===
{
  const s = newSlide(
    '[0:00] Hi — five minutes, so I am going to talk quickly.\n' +
    'acme-lan: an internal ACME server that hands out REAL, publicly-trusted certificates ' +
    'to hosts the internet has never heard of.\n' +
    'Pause on the joke about ACME Corp only if the room is warm.'
  )
  s.addText('$ certbot certonly --server http://acme-lan.lan:8000/acme/directory -d db.example.net', {
    x: 0.9, y: 0.75, w: 11.6, h: 0.35, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 13, color: BLUE,
  })
  s.addText('acme-lan', {
    x: 0.85, y: 1.7, w: 11.6, h: 1.7, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 96, bold: true, color: GOLD, valign: 'middle',
  })
  s.addText('Real, publicly-trusted certificates for the hosts\nthe internet can never reach.', {
    x: 0.9, y: 3.55, w: 11.4, h: 1.2, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 26, color: TEXT, lineSpacingMultiple: 1.15,
  })
  s.addText('No relation to the anvil company. Although both are elaborate schemes that mostly work.', {
    x: 0.9, y: 4.85, w: 11.4, h: 0.4, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 15, italic: true, color: MUTED,
  })
  s.addText('PyCon AU 2026  ·  Brisbane  ·  lightning talk  ·  github.com/smallsam/acme-lan  ·  MIT', {
    x: 0.9, y: 6.4, w: 11.6, h: 0.4, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 13, color: MUTED,
  })
}

// ========================================================= 2. thisisunsafe =
{
  const s = newSlide(
    '[0:12] This is the problem slide. Everyone in this room knows this string.\n' +
    'Type it into a Chrome interstitial, it clicks through. I know it by muscle memory. That is the bug.'
  )
  s.addText('thisisunsafe', {
    x: 0.85, y: 1.9, w: 12, h: 1.9, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 88, bold: true, color: GOLD, valign: 'middle',
  })
  s.addText('I have typed this so many times it stopped being a workaround\nand became a personality trait.', {
    x: 0.9, y: 4.05, w: 11.4, h: 1.1, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 24, color: TEXT, lineSpacingMultiple: 1.15,
  })
  kicker(s, '# the motivation, stated honestly')
}

// ======================================================== 3. split horizon =
{
  const s = newSlide(
    '[0:22] Here is the shape of the problem. One name, two worlds.\n' +
    'db.example.net is a real name in a real public zone. On the LAN it resolves to a private IP.\n' +
    'Let\'s Encrypt will happily certify that name — it just has to be able to check you own it.'
  )
  badge(s, 1)
  title(s, 'One name, two worlds')
  card(s, {
    x: 0.65, y: 1.55, w: 5.9, h: 2.55, eyebrow: 'PUBLIC VIEW', eyebrowColor: CORAL,
    head: 'db.example.net', headMono: true, headSize: 24,
    body: 'Not reachable. No open ports. Possibly no A record at all.\nThe CA cannot knock on this door.',
  })
  card(s, {
    x: 6.78, y: 1.55, w: 5.9, h: 2.55, eyebrow: 'LAN VIEW', eyebrowColor: GREEN,
    head: 'db.example.net → 192.168.3.5', headMono: true, headSize: 20,
    body: 'Split-horizon DNS. A real public domain, pointed at a box\nthat lives behind your firewall forever.',
  })
  s.addText([
    { text: 'The CA does not need to reach the box. ', options: { color: TEXT } },
    { text: 'It only needs proof you control the name.', options: { color: GOLD, bold: true } },
  ], {
    x: 0.65, y: 4.45, w: 12, h: 0.95, isTextBox: true, margin: 0, fontFace: SANS, fontSize: 25,
  })
  s.addText('That proof is a TXT record. Which means someone has to hold DNS credentials.', {
    x: 0.65, y: 5.5, w: 12, h: 0.5, isTextBox: true, margin: 0, fontFace: SANS, fontSize: 18, color: MUTED,
  })
  kicker(s, '# dns-01: prove the name, not the network path')
}

// ====================================================== 4. usual answers ===
{
  const s = newSlide(
    '[0:38] The three usual answers, and why I stopped liking all of them.\n' +
    'Tokens everywhere: a zone-wide credential on a printer. Private CA: now distribute a root to every device ' +
    'anyone ever brings. Self-signed: see the previous slide.'
  )
  badge(s, 2)
  title(s, 'The three usual answers')
  const y = 1.62, h = 3.9, w = 3.86
  card(s, {
    x: 0.65, y, w, h, eyebrow: 'OPTION A', eyebrowColor: CORAL,
    head: 'DNS token\non every host', headH: 1.05, headSize: 22,
    body: 'Every box that needs a cert now holds a credential that can rewrite your whole zone.\n\nIncluding the printer.',
  })
  card(s, {
    x: 4.73, y, w, h, eyebrow: 'OPTION B', eyebrowColor: CORAL,
    head: 'Run your own CA', headH: 1.05, headSize: 22,
    body: 'Genuinely fine — until you have to install that root on every laptop, phone, CI runner and contractor.\n\nForever.',
  })
  card(s, {
    x: 8.81, y, w, h, eyebrow: 'OPTION C', eyebrowColor: CORAL,
    head: 'Self-signed and\nlook away', headH: 1.05, headSize: 22,
    body: 'The industry standard.\n\nSee the previous slide.',
  })
  kicker(s, '# all three work. none of them made me happy.')
}

// ============================================================== 5. stats ===
{
  const s = newSlide(
    '[0:54] The numbers that made me build it. Zero of my LAN appliances will ever run an ACME client. ' +
    'One machine should hold the DNS credential. And the renewal has to be automatic, because 90 days comes around fast.'
  )
  badge(s, 3)
  title(s, 'Why I built it anyway', { color: TEXT })
  const stats = [
    { n: '0', l: 'appliances that will\never run certbot', c: CORAL },
    { n: '1', l: 'machine holding your\nDNS credentials', c: GOLD },
    { n: '90', l: 'days, renewed forever,\nwithout me', c: GREEN },
  ]
  stats.forEach((st, i) => {
    const x = 0.65 + i * 4.08
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 1.7, w: 3.86, h: 3.1, rectRadius: 0.09,
      fill: { color: PANEL }, line: { color: PANEL2, width: 1 }, shadow: shadow(),
    })
    s.addText(st.n, {
      x, y: 1.9, w: 3.86, h: 1.5, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 80, bold: true, color: st.c, align: 'center', valign: 'middle',
    })
    s.addText(st.l, {
      x: x + 0.3, y: 3.5, w: 3.26, h: 1.1, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 16, color: MUTED, align: 'center', valign: 'top', lineSpacingMultiple: 1.15,
    })
  })
  s.addText('ESXi. iDRAC. The core switch. The NAS. The printer. None of them will ever pip install anything.', {
    x: 0.65, y: 5.2, w: 12, h: 0.6, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 20, color: TEXT,
  })
  kicker(s, '# the printer has never installed anything. the printer barely prints.')
}

// =============================================================== 6. idea ===
{
  const s = newSlide(
    '[1:06] The idea is one sentence: be an ACME server on the inside, and an ACME client on the outside.\n' +
    'Your clients change exactly one thing — the directory URL.'
  )
  badge(s, 4)
  title(s, 'The whole idea')
  s.addText('Be an ACME server.\nBe an ACME client.\nSit in the middle.', {
    x: 0.9, y: 1.5, w: 8.6, h: 3.4, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 46, bold: true, color: GOLD, lineSpacingMultiple: 1.2, valign: 'middle',
  })
  card(s, {
    x: 9.0, y: 1.6, w: 3.7, h: 3.2, fill: PANEL2, eyebrow: 'CLIENT DIFF',
    head: 'One line.', headSize: 22,
    body: 'RFC 8555 both directions, so certbot and acme.sh need no plugin, no patch and no idea that anything unusual is happening.',
    bodyColor: TEXT,
  })
  s.addText('- --server https://acme-v02.api.letsencrypt.org/directory\n+ --server http://acme-lan.lan:8000/acme/directory', {
    x: 0.9, y: 5.25, w: 11.8, h: 1.0, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 17, color: GREEN, lineSpacingMultiple: 1.2,
  })
  kicker(s, '# no plugin, no patch, no idea anything unusual is happening')
}

// ======================================================= 7. architecture ===
{
  const s = newSlide(
    '[1:16] The architecture. Client talks ACME to me over the LAN and proves control with http-01 or tls-alpn-01. ' +
    'I turn around, open an order at the real CA for the same names, and prove control with DNS-01. ' +
    'Only this one box holds the DNS credential.'
  )
  badge(s, 5)
  title(s, 'The architecture, all of it')
  const y = 2.15, h = 1.55
  const boxes = [
    { x: 0.6, w: 3.4, head: 'certbot / acme.sh', sub: 'on the LAN · unmodified', border: PANEL2 },
    { x: 4.95, w: 3.45, head: 'acme-lan', sub: 'ACME server  +  ACME client', border: GOLD },
    { x: 9.35, w: 3.4, head: "Let's Encrypt", sub: 'ZeroSSL · EAB CA · private CA', border: PANEL2 },
  ]
  boxes.forEach((b) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: b.x, y, w: b.w, h, rectRadius: 0.09,
      fill: { color: b.border === GOLD ? PANEL2 : PANEL }, line: { color: b.border, width: b.border === GOLD ? 2.5 : 1 },
      shadow: shadow(),
    })
    s.addText(b.head, {
      x: b.x, y: y + 0.28, w: b.w, h: 0.5, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 22, bold: true, color: b.border === GOLD ? GOLD : TEXT, align: 'center',
    })
    s.addText(b.sub, {
      x: b.x + 0.15, y: y + 0.82, w: b.w - 0.3, h: 0.5, isTextBox: true, margin: 0,
      fontFace: MONO, fontSize: 11, color: MUTED, align: 'center',
    })
  })
  // arrows between the boxes
  const arrow = (x1, x2) => s.addShape(pres.ShapeType.line, {
    x: x1, y: y + h / 2, w: x2 - x1, h: 0,
    line: { color: GOLD, width: 2.25, endArrowType: 'triangle' },
  })
  arrow(4.05, 4.9)
  arrow(8.45, 9.3)
  const hop = (cx, top, bottom) => {
    s.addText([
      { text: top + '\n', options: { color: BLUE, bold: true } },
      { text: bottom, options: { color: MUTED } },
    ], {
      x: cx - 1.35, y: y - 1.0, w: 2.7, h: 0.85, isTextBox: true, margin: 0,
      fontFace: MONO, fontSize: 11, align: 'center', valign: 'bottom', lineSpacingMultiple: 1.2,
    })
  }
  hop(4.475, 'ACME  downstream', 'http-01 / tls-alpn-01')
  hop(8.875, 'ACME  upstream', 'dns-01')
  // the DNS hop
  s.addShape(pres.ShapeType.line, {
    x: 6.67, y: y + h, w: 0, h: 0.85, line: { color: GOLD, width: 2.25, endArrowType: 'triangle' },
  })
  s.addShape(pres.ShapeType.roundRect, {
    x: 4.35, y: 4.55, w: 4.65, h: 1.0, rectRadius: 0.09,
    fill: { color: PANEL }, line: { color: PANEL2, width: 1 }, shadow: shadow(),
  })
  s.addText('your public zone  /  acme-dns', {
    x: 4.35, y: 4.72, w: 4.65, h: 0.35, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 16, bold: true, color: TEXT, align: 'center',
  })
  s.addText('_acme-challenge.db.example.net  TXT', {
    x: 4.35, y: 5.08, w: 4.65, h: 0.35, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 11, color: GOLD, align: 'center',
  })
  s.addText('The only box on the\nLAN with a DNS\ncredential is this one.', {
    x: 9.35, y: 4.5, w: 3.4, h: 1.1, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 15, color: MUTED, lineSpacingMultiple: 1.15,
  })
  kicker(s, '# ~1400 lines of FastAPI standing between two ACME conversations')
}

// ================================================================ 8. CSR ===
{
  const s = newSlide(
    '[1:44] This is the one design decision that actually matters.\n' +
    'At finalize, the client sends me its CSR. I do not generate a key. I forward that same CSR upstream. ' +
    'So the cert that comes back matches the private key that never left the client.'
  )
  badge(s, 6)
  title(s, 'The one decision that matters')
  s.addText('acme-lan forwards your CSR upstream.', {
    x: 0.9, y: 1.35, w: 11.8, h: 1.0, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 42, bold: true, color: GOLD, valign: 'middle',
  })
  const rows = [
    ['The issued cert matches the key the client already has', GREEN],
    ['acme-lan never sees, stores or transmits that private key', GREEN],
    ['Renewal is just ACME again — no state to keep in sync', GREEN],
  ]
  rows.forEach(([t, c], i) => {
    const y = 2.65 + i * 0.72
    s.addShape(pres.ShapeType.ellipse, { x: 0.92, y: y + 0.09, w: 0.26, h: 0.26, fill: { color: c } })
    s.addText(t, {
      x: 1.42, y, w: 11.2, h: 0.45, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 20, color: TEXT, valign: 'middle',
    })
  })
  s.addText('order = upstream.new_order(csr_from_the_client)   # not one we made up', {
    x: 0.9, y: 5.2, w: 11.8, h: 0.5, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 15, color: BLUE,
  })
  kicker(s, '# a proxy that generated its own keys would be a very expensive self-signed cert')
}

// ===================================================== 9. downstream/up ====
{
  const s = newSlide(
    '[2:00] Two challenge conversations, and they are completely independent.\n' +
    'Downstream — proving to me, on the LAN — is http-01 or tls-alpn-01, so a box that only speaks TLS is fine.\n' +
    'Upstream — proving to Let\'s Encrypt — is DNS-01 by default, or edge http-01 if you are actually publicly reachable.'
  )
  badge(s, 7)
  title(s, 'Two challenges, two directions')
  card(s, {
    x: 0.65, y: 1.55, w: 5.9, h: 4.0, eyebrow: 'DOWNSTREAM  ·  PROVE IT TO ME', eyebrowColor: BLUE,
    head: 'http-01\ntls-alpn-01', headMono: true, headSize: 26, headH: 1.15, headColor: TEXT,
    body: 'Port 80 if the box has a web server.\n\nRFC 8737 over port 443 if it does not — the challenge rides in the TLS handshake itself.\n\nWhichever listener the appliance already has.',
  })
  card(s, {
    x: 6.78, y: 1.55, w: 5.9, h: 4.0, eyebrow: 'UPSTREAM  ·  PROVE IT TO THEM', eyebrowColor: GOLD,
    head: 'dns-01\nhttp-01 at the edge', headMono: true, headSize: 26, headH: 1.15, headColor: TEXT,
    body: 'dns-01 (default): nothing needs to be publicly reachable. Ever.\n\nedge http-01: faster than DNS propagation, but you need a public IP and a wildcard A record.\n\nOne env var switches it.',
  })
  kicker(s, 'ACME_LAN_UPSTREAM_CHALLENGE=dns-01')
}

// ================================================== 10. it is always DNS ===
{
  const s = newSlide(
    '[2:14] So DNS-01 it is. Which leaves one box holding a token that can rewrite your entire zone. ' +
    'That is better than thirty-seven copies of it. It is not actually good.'
  )
  s.addText('It’s always DNS.', {
    x: 0.85, y: 1.55, w: 11.8, h: 1.2, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 62, bold: true, color: GOLD, valign: 'middle',
  })
  s.addText('The protocol designers agreed with you so completely\nthey made a whole challenge type out of it.', {
    x: 0.9, y: 2.95, w: 11.6, h: 1.0, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 22, color: MUTED, lineSpacingMultiple: 1.15,
  })
  s.addShape(pres.ShapeType.roundRect, {
    x: 0.85, y: 4.35, w: 11.8, h: 1.5, rectRadius: 0.09,
    fill: { color: PANEL }, line: { color: CORAL, width: 2 }, shadow: shadow(),
  })
  s.addText('But now one box holds a token that can rewrite your whole zone.', {
    x: 1.2, y: 4.6, w: 11.1, h: 0.45, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 24, bold: true, color: TEXT,
  })
  s.addText('Better than thirty-seven copies of it. Still not something I want to leave lying around the LAN.', {
    x: 1.2, y: 5.12, w: 11.1, h: 0.45, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 17, color: MUTED,
  })
}

// ========================================================== 11. acme-dns ===
{
  const s = newSlide(
    '[2:22] So you chain it to acme-dns. Register once, get a random subdomain, and add ONE CNAME per name — ' +
    'a one-time change to your real zone. From then on acme-lan just POSTs the TXT value to acme-dns.\n' +
    'Removal is a no-op because acme-dns expires the records itself, which is the kind of API I like.'
  )
  badge(s, 8)
  title(s, 'Chaining to acme-dns')
  const steps = [
    { n: '1', h: 'Register once', b: 'acme-dns hands back a username, a password and a random subdomain.' },
    { n: '2', h: 'One CNAME, one time', b: '_acme-challenge.db.example.net\n→ a1b2c3.auth.example.net' },
    { n: '3', h: 'Then never touch DNS again', b: 'acme-lan POSTs the TXT value to /update. Removal is a no-op — acme-dns expires them itself.' },
  ]
  steps.forEach((st, i) => {
    const x = 0.65 + i * 4.08
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 1.5, w: 3.86, h: 3.2, rectRadius: 0.09,
      fill: { color: PANEL }, line: { color: PANEL2, width: 1 }, shadow: shadow(),
    })
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.32, y: 1.78, w: 0.5, h: 0.5, fill: { color: GOLD } })
    s.addText(st.n, {
      x: x + 0.32, y: 1.78, w: 0.5, h: 0.5, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 17, bold: true, color: INK, align: 'center', valign: 'middle',
    })
    s.addText(st.h, {
      x: x + 0.32, y: 2.45, w: 3.22, h: 0.75, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 19, bold: true, color: TEXT, valign: 'top',
    })
    s.addText(st.b, {
      x: x + 0.32, y: 3.25, w: 3.22, h: 1.25, isTextBox: true, margin: 0,
      fontFace: i === 1 ? MONO : SANS, fontSize: i === 1 ? 12 : 15, color: i === 1 ? GREEN : MUTED,
      valign: 'top', lineSpacingMultiple: 1.15,
    })
  })
  s.addText('acme-dns is a DNS server with exactly one opinion, and that opinion is “yes, that TXT record is mine”.', {
    x: 0.65, y: 5.1, w: 12, h: 0.6, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 19, italic: true, color: TEXT,
  })
  kicker(s, 'ACME_LAN_DNS_PROVIDER=acmedns   # or cloudflare')
}

// ====================================================== 12. blast radius ===
{
  const s = newSlide(
    '[2:46] Why bother? Blast radius.\n' +
    'A zone-wide token that leaks is a very bad afternoon. Leaked acme-dns credentials can set one TXT record ' +
    'on one delegated subdomain — worst case someone mints certs for the names you delegated. Bad, but bounded, and it cannot touch your MX records.'
  )
  badge(s, 9)
  title(s, 'Blast radius')
  card(s, {
    x: 0.65, y: 1.55, w: 5.9, h: 3.4, border: CORAL,
    eyebrow: 'IF THE ZONE TOKEN LEAKS', eyebrowColor: CORAL,
    head: 'Everything', headSize: 30, headH: 0.6,
    body: 'Rewrite any record in the zone. MX. SPF. Your mail. Your website. Certificates for anything you own.\n\nA very bad afternoon.',
    bodyColor: TEXT,
  })
  card(s, {
    x: 6.78, y: 1.55, w: 5.9, h: 3.4, border: GREEN,
    eyebrow: 'IF THE ACME-DNS CREDS LEAK', eyebrowColor: GREEN,
    head: 'One TXT record', headSize: 30, headH: 0.6,
    body: 'One delegated subdomain. Certificates for the names you pointed at it — and nothing else.\n\nBad, but bounded. Your MX records never even hear about it.',
    bodyColor: TEXT,
  })
  s.addText('Same protocol, one CNAME of separation.', {
    x: 0.65, y: 5.3, w: 12, h: 0.6, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 22, bold: true, color: GOLD,
  })
  kicker(s, '# CNAME _acme-challenge.db.example.net -> a1b2c3.auth.example.net')
}

// ======================================================= 13. device push ===
{
  const s = newSlide(
    '[2:58] Second half of the project: the things that will never run an ACME client at all.\n' +
    'Register the box as a managed host and acme-lan does issuance, installation and renewal for it.\n' +
    'Preferred mode: we fetch a CSR the DEVICE generated, sign it, and push back only the certificate.'
  )
  badge(s, 10)
  title(s, 'For the things that will never run ACME')
  card(s, {
    x: 0.65, y: 1.5, w: 5.9, h: 3.5, border: GREEN,
    eyebrow: 'MODE: DEVICE   (PREFERRED)', eyebrowColor: GREEN,
    head: 'The key never leaves the box', headSize: 22, headH: 0.55,
    body: 'Fetch a CSR the device generated itself, sign it upstream, push back only the certificate.\n\nNothing secret ever crosses the wire.',
  })
  card(s, {
    x: 6.78, y: 1.5, w: 5.9, h: 3.5, border: GOLD,
    eyebrow: 'MODE: LOCAL', eyebrowColor: GOLD,
    head: 'We make the key and push both', headSize: 22, headH: 0.55,
    body: 'For gear that cannot generate a CSR. The key is stored encrypted — never in plaintext at rest — and the UI tells you off about it anyway.',
  })
  s.addText('Install happens through deploy plugins: local (write files, run a reload) and ssh (SFTP + reload).\nMost network gear is driven over SSH, so a vendor plugin is one class and a list of PluginFields.', {
    x: 0.65, y: 5.2, w: 12, h: 1.0, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 17, color: MUTED, lineSpacingMultiple: 1.2,
  })
  kicker(s, 'ESXi · iDRAC · iLO · switches · printers · NAS · load balancers')
}

// ======================================================== 14. dashboard ====
{
  const s = newSlide(
    '[3:16] And yes, it has a dashboard. Every issued cert, what it is for, which device it was pushed to, ' +
    'and a live health badge — not what the database thinks, what the endpoint is actually serving right now.'
  )
  badge(s, 11)
  title(s, 'It comes with a dashboard')
  s.addText([
    { text: 'Every certificate, every managed host, one page.\n\n', options: { color: TEXT, fontSize: 19 } },
    { text: 'Live health badges are a raw TLS probe, not a database lookup.\n\n', options: { color: MUTED, fontSize: 17 } },
    { text: 'Certificates link back to the device they were pushed to, and back again.\n\n', options: { color: MUTED, fontSize: 17 } },
    { text: 'Expiry warnings, retire-when-done, email + webhook notifications.', options: { color: MUTED, fontSize: 17 } },
  ], {
    x: 0.72, y: 1.55, w: 4.85, h: 4.6, isTextBox: true, margin: 0,
    fontFace: SANS, valign: 'top', lineSpacingMultiple: 1.15,
  })
  shot(s, 'dashboard-full.png', { x: 5.9, y: 1.42, w: 6.76, h: 5.06 })
  kicker(s, '# GET /api/certificates · GET /api/hosts · POST /api/health/probe')
}

// ===================================================== 15. live health =====
{
  const s = newSlide(
    '[3:28] The health column is the bit I use most. It opens a raw TLS connection and reads the leaf certificate — ' +
    'so it works for LDAPS and SMTPS, not just HTTPS. Ten days left on the ESXi box, and it tells me before the ticket does.'
  )
  badge(s, 12)
  title(s, 'Live health, not a spreadsheet')
  shot(s, 'certs-table.png', { x: 0.7, y: 1.35, w: 11.93, h: 2.76 })
  shot(s, 'probe.png', { x: 0.7, y: 4.4, w: 5.5, h: 2.37 })
  s.addText([
    { text: 'A raw TLS handshake.\n', options: { fontSize: 24, bold: true, color: GOLD } },
    { text: 'Not an HTTP request that assumes port 443 speaks HTTP.\n\n', options: { fontSize: 17, color: TEXT } },
    { text: 'LDAPS. SMTPS. That one appliance on 8443. Anything that completes a handshake gets an honest answer: expiry, chain trust, SAN match, self-signed.', options: { fontSize: 16, color: MUTED } },
  ], {
    x: 6.55, y: 4.42, w: 6.15, h: 2.35, isTextBox: true, margin: 0,
    fontFace: SANS, valign: 'top', lineSpacingMultiple: 1.15,
  })
}

// ======================================================== 16. add host =====
{
  const s = newSlide(
    '[3:40] Adding a device used to be a raw JSON blob in a text box. Now plugins declare their config as ' +
    'PluginFields and the modal renders exactly the right form — and it changes as you switch plugin or CSR mode.'
  )
  badge(s, 13)
  title(s, 'Adding a device shouldn’t be a JSON blob')
  s.addText([
    { text: 'Plugins declare their own config.\n\n', options: { fontSize: 21, bold: true, color: GOLD } },
    { text: 'fields: ClassVar[list[PluginField]]\n\n', options: { fontSize: 14, color: GREEN, fontFace: MONO } },
    { text: 'The dashboard reads them from the API and renders the real form — filtered by the plugin you picked and the CSR mode you chose.\n\n', options: { fontSize: 16, color: MUTED } },
    { text: 'Write a plugin, get a UI. No frontend involved.', options: { fontSize: 17, color: TEXT } },
  ], {
    x: 0.72, y: 1.55, w: 4.45, h: 4.6, isTextBox: true, margin: 0,
    fontFace: SANS, valign: 'top', lineSpacingMultiple: 1.15,
  })
  shot(s, 'add-host-modal.png', { x: 5.52, y: 1.35, w: 7.2, h: 5.06 })
  kicker(s, '# GET /api/deploy-plugins -> the form builds itself')
}

// ==================================================== 17. alternatives =====
{
  const s = newSlide(
    '[3:50 — if you are behind, this is the slide to cut] Be honest about alternatives. Most people in this room do NOT need this. ' +
    'If your hosts can reach the internet and hold DNS credentials, use certbot with a DNS plugin and go and enjoy the hallway track.'
  )
  badge(s, 14)
  title(s, 'Should you use this? Probably not.')
  const rows = [
    ['Hosts reach the internet and can hold DNS creds', 'certbot + a DNS plugin. Go home.', MUTED],
    ['Happy to run a private CA and push a root everywhere', 'step-ca / smallstep. Genuinely excellent.', MUTED],
    ['You only need delegated DNS-01', 'acme-dns on its own. It is the good part of this talk.', MUTED],
    ['One reverse proxy fronts everything you own', 'Caddy or Traefik. Two lines of config.', MUTED],
    ['Appliances that can’t run ACME, split-horizon names, one place to see it all', '…fine. That one is this.', GOLD],
  ]
  rows.forEach(([l, r, c], i) => {
    const y = 1.5 + i * 1.02
    const last = i === rows.length - 1
    s.addShape(pres.ShapeType.roundRect, {
      x: 0.65, y, w: 12.03, h: 0.86, rectRadius: 0.07,
      fill: { color: last ? PANEL2 : PANEL }, line: { color: last ? GOLD : PANEL2, width: last ? 2 : 1 },
    })
    s.addText(l, {
      x: 0.95, y, w: 6.0, h: 0.86, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 15, color: last ? TEXT : MUTED, valign: 'middle',
    })
    s.addText(r, {
      x: 7.15, y, w: 5.35, h: 0.86, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 16, bold: true, color: c === GOLD ? GOLD : TEXT, valign: 'middle',
    })
  })
  kicker(s, '# a talk that tells you not to use the software is still a talk')
}

// ========================================================= 18. the python ==
{
  const s = newSlide(
    '[4:08] The Python, quickly. FastAPI and async SQLAlchemy, Alembic migrations that run on container start. ' +
    'The upstream client is certbot\'s own acme library — the reference implementation is right there on PyPI. ' +
    'And the end-to-end tests run against Pebble, a real ACME CA that issues deliberately awful certificates.'
  )
  badge(s, 15)
  title(s, 'The Python bits')
  const items = [
    ['FastAPI + async SQLAlchemy', 'One app. RFC 8555 endpoints, REST API, and the SPA, all from one process.'],
    ['certbot’s own acme library', 'The reference implementation is on PyPI. I did not write an ACME client.'],
    ['cryptography', 'CSRs, signing, and the raw TLS probe behind every health badge.'],
    ['Alembic on startup', 'The container migrates itself. Upgrades are docker pull.'],
    ['Pebble + pytest', 'A real ACME CA in a container that issues deliberately terrible certs. e2e for the whole chain.'],
    ['Vue 3 + Playwright', 'The dashboard, and UI tests in CI. Sorry — that bit is not Python.'],
  ]
  items.forEach(([h, b], i) => {
    const col = i % 2, row = Math.floor(i / 2)
    const x = 0.65 + col * 6.13, y = 1.5 + row * 1.72
    s.addShape(pres.ShapeType.roundRect, {
      x, y, w: 5.9, h: 1.5, rectRadius: 0.08, fill: { color: PANEL }, line: { color: PANEL2, width: 1 },
    })
    s.addText(h, {
      x: x + 0.28, y: y + 0.18, w: 5.34, h: 0.42, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 18, bold: true, color: GOLD, valign: 'middle',
    })
    s.addText(b, {
      x: x + 0.28, y: y + 0.62, w: 5.34, h: 0.7, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13.5, color: MUTED, valign: 'top', lineSpacingMultiple: 1.1,
    })
  })
  kicker(s, '# uv sync && uv run acme-lan')
}

// =========================================================== 19. lessons ===
{
  const s = newSlide(
    '[4:22] Three things I would tell past me. Forward the CSR — everything else follows from that. ' +
    'Stay on Let\'s Encrypt staging longer than you think. And no plaintext private keys at rest, ever, ' +
    'even the ones you generated yourself.'
  )
  badge(s, 16)
  title(s, 'Three things I’d tell past me')
  const lessons = [
    ['Forward the CSR.', 'Everything else in the design falls out of that one decision.', GOLD],
    ['Stay on staging longer.', 'Rate limits are a patient and thorough teacher.', GREEN],
    ['No plaintext keys at rest.', 'Fernet in the DB, or Key Vault, or Vault. Never a file on disk.', BLUE],
  ]
  lessons.forEach(([h, b, c], i) => {
    const y = 1.6 + i * 1.62
    s.addShape(pres.ShapeType.roundRect, {
      x: 0.65, y, w: 12.03, h: 1.35, rectRadius: 0.08, fill: { color: PANEL }, line: { color: PANEL2, width: 1 },
    })
    s.addShape(pres.ShapeType.ellipse, { x: 1.0, y: y + 0.45, w: 0.45, h: 0.45, fill: { color: c } })
    s.addText(String(i + 1), {
      x: 1.0, y: y + 0.45, w: 0.45, h: 0.45, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 16, bold: true, color: INK, align: 'center', valign: 'middle',
    })
    s.addText(h, {
      x: 1.7, y: y + 0.2, w: 10.6, h: 0.5, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 24, bold: true, color: TEXT, valign: 'middle',
    })
    s.addText(b, {
      x: 1.7, y: y + 0.72, w: 10.6, h: 0.45, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 16, color: MUTED, valign: 'middle',
    })
  })
  kicker(s, '# the staging environment exists because I do')
}

// ============================================================ 20. try it ===
{
  const s = newSlide(
    '[4:36] One docker run, defaults to Let\'s Encrypt staging so you cannot hurt yourself. MIT, on GitHub.\n' +
    'Thank you — no questions, lightning talk rules, but I will be in the hallway and my printer finally has a valid certificate.'
  )
  s.addText('Try it', {
    x: 0.85, y: 0.75, w: 11.8, h: 0.9, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 44, bold: true, color: GOLD, valign: 'middle',
  })
  s.addShape(pres.ShapeType.roundRect, {
    x: 0.85, y: 1.85, w: 11.8, h: 2.15, rectRadius: 0.09,
    fill: { color: '04101E' }, line: { color: PANEL2, width: 1 }, shadow: shadow(),
  })
  s.addText(
    'docker run -d --name acme-lan -p 8000:8000 -v acme-lan-data:/app/data \\\n' +
    '  -e ACME_LAN_EXTERNAL_URL="http://acme-lan.example.net:8000" \\\n' +
    '  -e ACME_LAN_SECRET_KEY="$(...fernet key...)" \\\n' +
    '  -e ACME_LAN_DNS_PROVIDER="acmedns" \\\n' +
    '  ghcr.io/smallsam/acme-lan:latest      # defaults to LE staging',
    {
      x: 1.15, y: 2.05, w: 11.2, h: 1.75, isTextBox: true, margin: 0,
      fontFace: MONO, fontSize: 14, color: GREEN, valign: 'top', lineSpacingMultiple: 1.2,
    }
  )
  s.addText('github.com/smallsam/acme-lan', {
    x: 0.85, y: 4.3, w: 11.8, h: 0.7, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 34, bold: true, color: TEXT, valign: 'middle',
  })
  s.addText('MIT · docs for deployment, plugins and key handling in the repo · issues and vendor plugins very welcome', {
    x: 0.85, y: 5.0, w: 11.8, h: 0.45, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 16, color: MUTED,
  })
  s.addText('Thanks. No questions — lightning talk rules — but I’m in the hallway,\nand my printer finally has a certificate nobody has to click through.', {
    x: 0.85, y: 5.65, w: 11.8, h: 1.0, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 19, italic: true, color: GOLD, lineSpacingMultiple: 1.15,
  })
}

await pres.writeFile({ fileName: OUT })
console.log('wrote', OUT)
