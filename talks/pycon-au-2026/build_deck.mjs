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
// PyCon AU 2026 brand colours: violet on a light grey ground, with lavender,
// coral, lime and jade as the accent family.
const VIOLET = '4B18E8' // the dominant brand colour
const VIOLET_DEEP = '2E0C93' // code and small type on the light ground
const VIOLET_MID = '6B4EF0' // kickers, secondary marks
const LAVENDER = 'B18CFA' // secondary text on violet slides
const LIME = 'C2F166' // the accent on violet slides
const JADE = '1F8A4F' // "good news" — darkened for contrast on light grey
const CORAL = 'EF5539' // "bad news"
const ACCENT = VIOLET // the sharp accent on light slides

const GROUND = 'EAEAEA' // light slide ground
const CARD = 'FFFFFF'
const CARD_ALT = 'EDE8FD'
const BORDER = 'CFC6EE'
const INK = '1A1533' // body text on light
const MUTED = '5F5878'
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

function newSlide(notes, bg = GROUND) {
  const s = pres.addSlide()
  s.background = { color: bg }
  if (notes) s.addNotes(notes)
  return s
}

/** Gold numbered badge — the deck's repeating motif. */
function badge(s, label) {
  s.addShape(pres.ShapeType.ellipse, { x: 0.62, y: 0.42, w: 0.62, h: 0.62, fill: { color: ACCENT } })
  s.addText(String(label), {
    x: 0.62, y: 0.42, w: 0.62, h: 0.62, isTextBox: true, margin: 0,
    align: 'center', valign: 'middle', fontFace: SANS, fontSize: 20, bold: true, color: WHITE,
  })
}

function title(s, text, opts = {}) {
  s.addText(text, {
    x: 1.45, y: 0.36, w: 11.3, h: 0.78, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: opts.fontSize || 34, bold: true, color: opts.color || INK,
    align: 'left', valign: 'middle',
  })
}

/** Monospace kicker line, bottom-left. */
function kicker(s, text, color = VIOLET_MID) {
  s.addText(text, {
    x: 0.65, y: 6.72, w: 12.1, h: 0.4, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 12, color, align: 'left', valign: 'middle',
  })
}

/** A card: rounded panel + heading + body lines. */
function card(s, o) {
  s.addShape(pres.ShapeType.roundRect, {
    x: o.x, y: o.y, w: o.w, h: o.h, rectRadius: 0.09,
    fill: { color: o.fill || CARD }, line: { color: o.border || BORDER, width: 1 }, shadow: shadow(),
  })
  let cursor = o.y + 0.28
  if (o.eyebrow) {
    s.addText(o.eyebrow, {
      x: o.x + 0.32, y: cursor, w: o.w - 0.64, h: 0.28, isTextBox: true, margin: 0,
      fontFace: MONO, fontSize: 12, bold: true, color: o.eyebrowColor || ACCENT, charSpacing: 1,
    })
    cursor += 0.36
  }
  if (o.head) {
    const hh = o.headH || 0.5
    s.addText(o.head, {
      x: o.x + 0.32, y: cursor, w: o.w - 0.64, h: hh, isTextBox: true, margin: 0,
      fontFace: o.headMono ? MONO : SANS, fontSize: o.headSize || 22, bold: true,
      color: o.headColor || INK, valign: 'top',
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

/** A full-bleed violet section divider. */
function divider(s, head, sub, kick) {
  s.addText(head, {
    x: 0.85, y: 2.2, w: 11.8, h: 1.4, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 54, bold: true, color: LIME, valign: 'middle',
  })
  s.addText(sub, {
    x: 0.9, y: 3.75, w: 11.6, h: 1.0, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 22, color: WHITE, lineSpacingMultiple: 1.15,
  })
  if (kick) kicker(s, kick, LAVENDER)
}

/** Rounded white plate behind a light-UI screenshot. */
function shot(s, file, o) {
  s.addShape(pres.ShapeType.roundRect, {
    x: o.x - 0.09, y: o.y - 0.09, w: o.w + 0.18, h: o.h + 0.18, rectRadius: 0.07,
    fill: { color: WHITE }, line: { color: BORDER, width: 1 },
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
    'Pause on the joke about ACME Corp only if the room is warm.',
    VIOLET
  )
  s.addText('$ certbot certonly --server http://acme-lan.lan:8000/acme/directory -d db.example.net', {
    x: 0.9, y: 0.75, w: 11.6, h: 0.35, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 13, color: LAVENDER,
  })
  s.addText('acme-lan', {
    x: 0.85, y: 1.7, w: 11.6, h: 1.7, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 96, bold: true, color: LIME, valign: 'middle',
  })
  s.addText('Real, publicly-trusted certificates for the hosts\nthe internet can never reach.', {
    x: 0.9, y: 3.55, w: 11.4, h: 1.2, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 26, color: WHITE, lineSpacingMultiple: 1.15,
  })
  s.addText('No relation to the anvil company. Although both are elaborate schemes that mostly work.', {
    x: 0.9, y: 4.85, w: 11.4, h: 0.4, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 15, italic: true, color: LAVENDER,
  })
  s.addText('PyCon AU 2026  ·  Brisbane  ·  lightning talk  ·  github.com/smallsam/acme-lan  ·  MIT', {
    x: 0.9, y: 6.4, w: 11.6, h: 0.4, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 13, color: LAVENDER,
  })
}

// ======================================================== 3. split horizon =
{
  const s = newSlide(
    '[0:12] Here is the shape of the problem. One name, two worlds.\n' +
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
    x: 6.78, y: 1.55, w: 5.9, h: 2.55, eyebrow: 'LAN VIEW', eyebrowColor: JADE,
    head: 'db.example.net → 192.168.3.5', headMono: true, headSize: 20,
    body: 'Split-horizon DNS. A real public domain, pointed at a box\nthat lives behind your firewall forever.',
  })
  s.addText([
    { text: 'The CA does not need to reach the box. ', options: { color: INK } },
    { text: 'It only needs proof you control the name.', options: { color: ACCENT, bold: true } },
  ], {
    x: 0.65, y: 4.45, w: 12, h: 0.95, isTextBox: true, margin: 0, fontFace: SANS, fontSize: 25,
  })
  s.addText('That proof is a TXT record. Which means someone has to hold DNS credentials.', {
    x: 0.65, y: 5.5, w: 12, h: 0.5, isTextBox: true, margin: 0, fontFace: SANS, fontSize: 18, color: MUTED,
  })
  kicker(s, '# dns-01: prove the name, not the network path')
}

// ================================================= 3. how acme works =======
{
  const s = newSlide(
    '[0:32] Quick recap of how ACME actually works, because the whole talk hangs off it.\n' +
    'A CA will certify any name you can prove you control, and there are three ways to prove it: ' +
    'serve a token over HTTP, answer a special TLS handshake, or publish a TXT record.\n' +
    'Only the last one works when the CA can never reach the box.'
  )
  badge(s, 2)
  title(s, 'How ACME actually works')
  s.addText('A CA will certify any name you can prove you control. Three ways to prove it:', {
    x: 0.72, y: 1.25, w: 12, h: 0.5, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 20, color: INK,
  })
  const ch = [
    { k: 'http-01', t: 'Serve a token', b: 'Put it at /.well-known/acme-challenge/… and the CA fetches it over port 80.', c: BORDER },
    { k: 'tls-alpn-01', t: 'Answer a handshake', b: 'The token rides inside a special TLS handshake on 443. No HTTP server needed. (RFC 8737)', c: BORDER },
    { k: 'dns-01', t: 'Publish a TXT record', b: 'At _acme-challenge.<name>. The CA looks it up. Nothing of yours has to be reachable at all.', c: JADE },
  ]
  ch.forEach((o, i) => {
    const x = 0.65 + i * 4.08
    card(s, {
      x, y: 1.95, w: 3.86, h: 3.05, border: o.c,
      eyebrow: o.k.toUpperCase(), eyebrowColor: o.c === JADE ? JADE : VIOLET,
      head: o.t, headSize: 20, headH: 0.55,
      body: o.b, bodyColor: INK,
    })
  })
  s.addText('Your LAN host can never answer the first two from the internet. So: dns-01.', {
    x: 0.65, y: 5.25, w: 12, h: 0.55, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 22, bold: true, color: VIOLET,
  })
  kicker(s, '# the CA never has to see your host — only your proof')
}

// ======================================================= 4. prerequisite ===
{
  const s = newSlide(
    '[0:54] One prerequisite, and it is not negotiable: the names on your LAN have to be real, public names. ' +
    'No .local, no .internal, no .lan — a public CA will not certify a name nobody owns.\n' +
    'The good news is that split-horizon DNS stopped being painful. unbound and dnsmasq will override just the ' +
    'names you host and pass the rest of the zone straight through.'
  )
  badge(s, 3)
  title(s, 'The one prerequisite')
  s.addText('Your internal names have to be public names.', {
    x: 0.9, y: 1.28, w: 11.8, h: 0.85, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 34, bold: true, color: ACCENT, valign: 'middle',
  })
  card(s, {
    x: 0.65, y: 2.3, w: 5.9, h: 2.9, border: CORAL,
    eyebrow: 'NOT NEGOTIABLE', eyebrowColor: CORAL,
    head: 'No .local. No .internal. No .lan.', headSize: 21, headH: 0.55,
    body: 'A public CA will not certify a name nobody owns. You need a real, registered zone.\n\nGood time to use that two-letter domain you have been hoarding.',
    bodyColor: INK,
  })
  card(s, {
    x: 6.78, y: 2.3, w: 5.9, h: 2.9, border: JADE,
    eyebrow: 'GOOD NEWS', eyebrowColor: JADE,
    head: 'Split horizon stopped hurting', headSize: 21, headH: 0.55,
    body: 'No second copy of the zone to keep in sync. Override only the names you host on the LAN; everything else resolves normally.',
    bodyColor: INK,
  })
  s.addText(
    'unbound   local-zone: "example.net." transparent\n' +
    'dnsmasq   address=/db.example.net/192.168.3.5',
    {
      x: 0.9, y: 5.45, w: 11.8, h: 1.0, isTextBox: true, margin: 0,
      fontFace: MONO, fontSize: 15, color: VIOLET_DEEP, lineSpacingMultiple: 1.25,
    }
  )
  kicker(s, '# one line per host, and the rest of your zone never notices')
}

// ====================================================== 4. usual answers ===
{
  const s = newSlide(
    '[1:12] The three usual answers, and why I stopped liking all of them.\n' +
    'Tokens everywhere: a zone-wide credential on a printer. Private CA: now distribute a root to every device ' +
    'anyone ever brings. Self-signed: every browser warning you have ever clicked through.'
  )
  badge(s, 4)
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
    body: 'The industry standard.\n\nEvery browser warning you have clicked through, and every one you have taught somebody else to click through.',
  })
  s.addText('* Yes — you can shrink that token by delegating _acme-challenge to a zone of its own. Hold that thought; we come back to it.', {
    x: 0.65, y: 5.7, w: 12, h: 0.45, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 15, italic: true, color: MUTED,
  })
  kicker(s, '# all three work. none of them made me happy.')
}

// =============================================================== 6. idea ===
{
  const s = newSlide(
    '[1:32] The idea is one sentence: be an ACME server on the inside, and an ACME client on the outside.\n' +
    'Your clients change exactly one thing — the directory URL.'
  )
  badge(s, 5)
  title(s, 'The whole idea')
  s.addText('Be an ACME server.\nBe an ACME client.\nSit in the middle.', {
    x: 0.9, y: 1.5, w: 8.6, h: 3.4, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 46, bold: true, color: ACCENT, lineSpacingMultiple: 1.2, valign: 'middle',
  })
  card(s, {
    x: 9.0, y: 1.6, w: 3.7, h: 3.2, fill: CARD_ALT, eyebrow: 'CLIENT DIFF',
    head: 'One line.', headSize: 22,
    body: 'RFC 8555 both directions, so certbot, acme.sh and the ACME client already built into Proxmox need no plugin, no patch and no idea anything unusual is happening.',
    bodyColor: INK,
  })
  s.addText('- --server https://acme-v02.api.letsencrypt.org/directory\n+ --server http://acme-lan.lan:8000/acme/directory', {
    x: 0.9, y: 5.25, w: 11.8, h: 1.0, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 17, color: VIOLET_DEEP, lineSpacingMultiple: 1.2,
  })
  kicker(s, '# stock clients only. nothing that needs a custom hook script.')
}

// ======================================================= 7. architecture ===
{
  const s = newSlide(
    '[1:48] The architecture. Client talks ACME to me over the LAN and proves control with http-01 or tls-alpn-01. ' +
    'I turn around, open an order at the real CA for the same names, and prove control with DNS-01 — writing the TXT ' +
    'into a zone I delegated for exactly this.\n' +
    'Only this one box holds a DNS credential, and it is a small one.'
  )
  badge(s, 6)
  title(s, 'The architecture, all of it')
  const y = 2.15, h = 1.55
  const boxes = [
    { x: 0.6, w: 3.4, head: 'certbot · acme.sh', sub: 'proxmox · truenas · unmodified', border: CARD_ALT },
    { x: 4.95, w: 3.45, head: 'acme-lan', sub: 'ACME server  +  ACME client', border: ACCENT },
    { x: 9.35, w: 3.4, head: "Let's Encrypt", sub: 'ZeroSSL · EAB CA · private CA', border: CARD_ALT },
  ]
  boxes.forEach((b) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: b.x, y, w: b.w, h, rectRadius: 0.09,
      fill: { color: b.border === ACCENT ? VIOLET : CARD }, line: { color: b.border, width: b.border === ACCENT ? 2.5 : 1 },
      shadow: shadow(),
    })
    s.addText(b.head, {
      x: b.x, y: y + 0.28, w: b.w, h: 0.5, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 22, bold: true, color: b.border === ACCENT ? WHITE : INK, align: 'center',
    })
    s.addText(b.sub, {
      x: b.x + 0.15, y: y + 0.82, w: b.w - 0.3, h: 0.5, isTextBox: true, margin: 0,
      fontFace: MONO, fontSize: 11, color: b.border === ACCENT ? LAVENDER : MUTED, align: 'center',
    })
  })
  // arrows between the boxes
  const arrow = (x1, x2) => s.addShape(pres.ShapeType.line, {
    x: x1, y: y + h / 2, w: x2 - x1, h: 0,
    line: { color: ACCENT, width: 2.25, endArrowType: 'triangle' },
  })
  arrow(4.05, 4.9)
  arrow(8.45, 9.3)
  const hop = (cx, top, bottom) => {
    s.addText([
      { text: top + '\n', options: { color: VIOLET_MID, bold: true } },
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
    x: 6.67, y: y + h, w: 0, h: 0.85, line: { color: ACCENT, width: 2.25, endArrowType: 'triangle' },
  })
  s.addShape(pres.ShapeType.roundRect, {
    x: 4.35, y: 4.55, w: 4.65, h: 1.0, rectRadius: 0.09,
    fill: { color: CARD }, line: { color: CARD_ALT, width: 1 }, shadow: shadow(),
  })
  s.addText('your delegated _acme-challenge zone', {
    x: 4.35, y: 4.72, w: 4.65, h: 0.35, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 16, bold: true, color: INK, align: 'center',
  })
  s.addText('_acme-challenge.db.example.net  TXT', {
    x: 4.35, y: 5.08, w: 4.65, h: 0.35, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 11, color: ACCENT, align: 'center',
  })
  s.addText('The only box on the\nLAN with a DNS\ncredential is this one.', {
    x: 9.35, y: 4.5, w: 3.4, h: 1.1, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 15, color: MUTED, lineSpacingMultiple: 1.15,
  })
  kicker(s, '# ~5k lines of Python standing between two ACME conversations')
}

// ================================================================ 8. CSR ===
{
  const s = newSlide(
    '[2:18] This is the one design decision that actually matters.\n' +
    'At finalize, the client sends me its CSR. I do not generate a key. I forward that same CSR upstream. ' +
    'So the cert that comes back matches the private key that never left the client.'
  )
  badge(s, 7)
  title(s, 'The one decision that matters')
  s.addText('acme-lan forwards your CSR upstream.', {
    x: 0.9, y: 1.35, w: 11.8, h: 1.0, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 42, bold: true, color: ACCENT, valign: 'middle',
  })
  const rows = [
    ['The issued cert matches the key the client already has', JADE],
    ['acme-lan never sees, stores or transmits that private key', JADE],
    ['Renewal is just ACME again — no state to keep in sync', JADE],
  ]
  rows.forEach(([t, c], i) => {
    const y = 2.65 + i * 0.72
    s.addShape(pres.ShapeType.ellipse, { x: 0.92, y: y + 0.09, w: 0.26, h: 0.26, fill: { color: c } })
    s.addText(t, {
      x: 1.42, y, w: 11.2, h: 0.45, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 20, color: INK, valign: 'middle',
    })
  })
  s.addText('order = upstream.new_order(csr_from_the_client)   # not one we made up', {
    x: 0.9, y: 5.2, w: 11.8, h: 0.5, isTextBox: true, margin: 0,
    fontFace: MONO, fontSize: 15, color: VIOLET_MID,
  })
  kicker(s, '# a proxy that generated its own keys would be a very expensive self-signed cert')
}

// ============================================== 9. where the creds live ====
{
  const s = newSlide(
    '[2:38] So where do the DNS credentials live? Three options, and they get better on two axes at once: ' +
    'how much a leaked credential can do, and how many places you have to go when you rotate it.\n' +
    'Option two — CNAME _acme-challenge at a zone of its own — is the trick I promised you earlier. ' +
    'Option three is this project: keep that narrow credential, and put it in exactly one place.'
  )
  badge(s, 8)
  title(s, 'Where the DNS credentials live')
  const opts = [
    {
      c: CORAL, e: 'OPTION 1',
      h: 'Zone creds,\nevery host',
      b: 'A token that can rewrite the whole zone — your MX, your website — copied onto every box that needs a cert.\n\nRotating means touching all of them.',
    },
    {
      c: VIOLET, e: 'OPTION 2',
      h: 'Delegated creds,\nevery host',
      b: 'CNAME _acme-challenge to a zone of its own, so the token can only write there.\n\nMuch smaller blast radius. Still on every box, still rotated everywhere.',
    },
    {
      c: JADE, e: 'OPTION 3  ·  ACME-LAN',
      h: 'Delegated creds,\none host',
      b: 'The same narrow token, held in one place. Every other box speaks plain ACME and holds nothing at all.\n\nRotate it once.',
    },
  ]
  opts.forEach((o, i) => {
    const x = 0.65 + i * 4.08
    card(s, {
      x, y: 1.45, w: 3.86, h: 3.85, border: o.c,
      eyebrow: o.e, eyebrowColor: o.c,
      head: o.h, headSize: 21, headH: 1.0,
      body: o.b, bodyColor: INK, bodySize: 14,
    })
  })
  s.addText([
    { text: 'Two axes at once: ', options: { color: INK } },
    { text: 'what a leaked credential can do, and how many places you have to fix.', options: { color: VIOLET, bold: true } },
  ], {
    x: 0.65, y: 5.55, w: 12, h: 0.55, isTextBox: true, margin: 0, fontFace: SANS, fontSize: 21,
  })
  kicker(s, '# the CNAME is the good idea. one holder for it is the better one.')
}

// ============================================== 10. extras divider =========
{
  const s = newSlide(
    '[3:08] That is the whole core idea. Everything after this is scope creep I am happy about.',
    VIOLET
  )
  divider(
    s,
    'That’s the core.',
    'Everything after this is scope creep I’m happy about —\nand the reason I actually still run it.',
    '# extras'
  )
}

// ======================================================= 13. device push ===
{
  const s = newSlide(
    '[3:14] Extra number one: the things that will never run an ACME client at all.\n' +
    'Register the box as a managed host and acme-lan does issuance, installation and renewal for it.\n' +
    'Preferred mode: we fetch a CSR the DEVICE generated, sign it, and push back only the certificate.'
  )
  badge(s, 9)
  title(s, 'For the things that will never run ACME')
  card(s, {
    x: 0.65, y: 1.5, w: 5.9, h: 3.5, border: JADE,
    eyebrow: 'MODE: DEVICE   (PREFERRED)', eyebrowColor: JADE,
    head: 'The key never leaves the box', headSize: 22, headH: 0.55,
    body: 'Fetch a CSR the device generated itself, sign it upstream, push back only the certificate.\n\nNothing secret ever crosses the wire.',
  })
  card(s, {
    x: 6.78, y: 1.5, w: 5.9, h: 3.5, border: ACCENT,
    eyebrow: 'MODE: LOCAL', eyebrowColor: ACCENT,
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
    '[3:36] And yes, it has a dashboard. Every issued cert, what it is for, which device it was pushed to, ' +
    'and a live health badge — not what the database thinks, what the endpoint is actually serving right now.'
  )
  badge(s, 10)
  title(s, 'It comes with a dashboard')
  s.addText([
    { text: 'Every certificate, every managed host, one page.\n\n', options: { color: INK, fontSize: 19 } },
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
    '[3:52] The health column is the bit I use most. It opens a raw TLS connection and reads the leaf certificate — ' +
    'so it works for LDAPS and SMTPS, not just HTTPS. Ten days left on the ESXi box, and it tells me before the ticket does.'
  )
  badge(s, 11)
  title(s, 'Live health, not a spreadsheet')
  shot(s, 'certs-table.png', { x: 0.7, y: 1.35, w: 11.93, h: 2.76 })
  shot(s, 'probe.png', { x: 0.7, y: 4.4, w: 5.5, h: 2.37 })
  s.addText([
    { text: 'A raw TLS handshake.\n', options: { fontSize: 24, bold: true, color: ACCENT } },
    { text: 'Not an HTTP request that assumes port 443 speaks HTTP.\n\n', options: { fontSize: 17, color: INK } },
    { text: 'LDAPS. SMTPS. That one appliance on 8443. Anything that completes a handshake gets an honest answer: expiry, chain trust, SAN match, self-signed.', options: { fontSize: 16, color: MUTED } },
  ], {
    x: 6.55, y: 4.42, w: 6.15, h: 2.35, isTextBox: true, margin: 0,
    fontFace: SANS, valign: 'top', lineSpacingMultiple: 1.15,
  })
}

// ================================================ 14. should you use it ====
{
  const s = newSlide(
    '[4:08] Should you use it? Maybe! Which is a stronger answer than it sounds.\n' +
    'If your hosts reach the internet and can hold DNS credentials, you do not need me. But if you want ' +
    'delegated DNS-01 with the clients you already have, the alternative — as far as I know — is standing up ' +
    'acme-dns, and that is more work than this.'
  )
  badge(s, 12)
  title(s, 'Should you use this? Maybe!')
  const rows = [
    ['Your hosts reach the internet and can hold DNS creds', 'certbot + a DNS plugin. You don’t need me.', false],
    ['One reverse proxy already fronts everything you own', 'Caddy or Traefik. Two lines of config.', false],
    ['Happy to run a private CA and push a root everywhere', 'step-ca / smallstep. Genuinely excellent.', false],
    ['You want delegated DNS-01 — with the clients you already have', 'This. The alternative is standing up acme-dns.', true],
  ]
  rows.forEach(([l, r, last], i) => {
    const y = 1.55 + i * 1.16
    s.addShape(pres.ShapeType.roundRect, {
      x: 0.65, y, w: 12.03, h: 0.98, rectRadius: 0.07,
      fill: { color: last ? CARD_ALT : CARD }, line: { color: last ? VIOLET : BORDER, width: last ? 2 : 1 },
    })
    s.addText(l, {
      x: 0.95, y, w: 6.1, h: 0.98, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 15, color: last ? INK : MUTED, valign: 'middle',
    })
    s.addText(r, {
      x: 7.25, y, w: 5.25, h: 0.98, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 16, bold: true, color: last ? VIOLET : INK, valign: 'middle',
    })
  })
  s.addText('It is at least easier than the thing I would otherwise be telling you to build.', {
    x: 0.65, y: 6.25, w: 12, h: 0.45, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 17, italic: true, color: MUTED,
  })
}

// ========================================================= 18. the python ==
{
  const s = newSlide(
    '[4:26] The Python, quickly. FastAPI and async SQLAlchemy, Alembic migrations that run on container start. ' +
    'The upstream client is certbot\'s own acme library — the reference implementation is right there on PyPI. ' +
    'And the end-to-end tests run against Pebble, a real ACME CA that issues deliberately awful certificates.'
  )
  badge(s, 13)
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
      x, y, w: 5.9, h: 1.5, rectRadius: 0.08, fill: { color: CARD }, line: { color: CARD_ALT, width: 1 },
    })
    s.addText(h, {
      x: x + 0.28, y: y + 0.18, w: 5.34, h: 0.42, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 18, bold: true, color: ACCENT, valign: 'middle',
    })
    s.addText(b, {
      x: x + 0.28, y: y + 0.62, w: 5.34, h: 0.7, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13.5, color: MUTED, valign: 'top', lineSpacingMultiple: 1.1,
    })
  })
  kicker(s, '# uv sync && uv run acme-lan')
}

// ============================================================ 20. try it ===
{
  const s = newSlide(
    '[4:42] One docker run, defaults to Let\'s Encrypt staging so you cannot hurt yourself. MIT, on GitHub.\n' +
    'Thank you — no questions, lightning talk rules — but I will be in the hallway and my printer finally has a valid certificate.',
    VIOLET
  )
  s.addText('Try it', {
    x: 0.85, y: 0.75, w: 11.8, h: 0.9, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 44, bold: true, color: LIME, valign: 'middle',
  })
  s.addShape(pres.ShapeType.roundRect, {
    x: 0.85, y: 1.85, w: 11.8, h: 2.15, rectRadius: 0.09,
    fill: { color: VIOLET_DEEP }, line: { color: '5B2BEF', width: 1 },
  })
  s.addText(
    'docker run -d --name acme-lan -p 8000:8000 -v acme-lan-data:/app/data \\\n' +
    '  -e ACME_LAN_EXTERNAL_URL="http://acme-lan.example.net:8000" \\\n' +
    '  -e ACME_LAN_SECRET_KEY="$(...fernet key...)" \\\n' +
    '  -e ACME_LAN_DNS_PROVIDER="cloudflare" \\\n' +
    '  ghcr.io/smallsam/acme-lan:latest      # defaults to LE staging',
    {
      x: 1.15, y: 2.05, w: 11.2, h: 1.75, isTextBox: true, margin: 0,
      fontFace: MONO, fontSize: 14, color: LIME, valign: 'top', lineSpacingMultiple: 1.2,
    }
  )
  s.addText('github.com/smallsam/acme-lan', {
    x: 0.85, y: 4.3, w: 11.8, h: 0.7, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 34, bold: true, color: WHITE, valign: 'middle',
  })
  s.addText('MIT · docs for deployment, plugins and key handling in the repo · issues and vendor plugins very welcome', {
    x: 0.85, y: 5.0, w: 11.8, h: 0.45, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 16, color: LAVENDER,
  })
  s.addText('Thanks. No questions — lightning talk rules — but I’m in the hallway,\nand my printer finally has a certificate nobody has to click through.', {
    x: 0.85, y: 5.65, w: 11.8, h: 1.0, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 19, italic: true, color: LIME, lineSpacingMultiple: 1.15,
  })
}

// ============================================== 17. appendix divider =======
{
  const s = newSlide(
    '[appendix] Do not present these. They are here for the hallway conversation afterwards.',
    VIOLET
  )
  divider(
    s,
    'Appendix',
    'Prior art, and the bit about challenge directions\nthat did not fit in five minutes.',
    '# for the hallway track'
  )
}

// ================================================= 18. prior art ===========
{
  const s = newSlide(
    '[appendix] Prior art. acme-dns is a tiny DNS server whose entire job is answering _acme-challenge — ' +
    'a lovely idea, but it is an internet-facing DNS server to run, and clients have to speak acme-dns, ' +
    'which most appliances never will.\n' +
    'acme2certifier is an ACME server that fronts other CAs through ca_handler plugins; that is where ' +
    'acme-lan\'s private-CA handler comes from. Neither did the split-horizon and device-push half I wanted, ' +
    'so acme-lan borrows from both.'
  )
  title(s, 'Prior art I borrowed from')
  card(s, {
    x: 0.65, y: 1.5, w: 5.9, h: 3.6, border: VIOLET,
    eyebrow: 'ACME-DNS', eyebrowColor: VIOLET,
    head: 'A DNS server with one opinion', headSize: 21, headH: 0.55,
    body: 'Its entire job is answering _acme-challenge, and it expires its own records. Lovely idea — but it is an internet-facing DNS server you run, and clients have to speak acme-dns. Most appliances never will.\n\nacme-lan ships a provider for it anyway.',
    bodyColor: INK,
  })
  card(s, {
    x: 6.78, y: 1.5, w: 5.9, h: 3.6, border: VIOLET,
    eyebrow: 'ACME2CERTIFIER', eyebrowColor: VIOLET,
    head: 'ACME in front of other CAs', headSize: 21, headH: 0.55,
    body: 'Fronts a CA that is not Let’s Encrypt through ca_handler plugins. That is exactly where acme-lan’s private-CA handler comes from.\n\nBut it does not do the split-horizon or device-push half.',
    bodyColor: INK,
  })
  s.addText('Both solve part of it. Neither solved it the way I wanted — so this borrows from both.', {
    x: 0.65, y: 5.35, w: 12, h: 0.55, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 21, bold: true, color: VIOLET,
  })
  kicker(s, '# appendix · standing on shoulders, then wandering off')
}

// ===================================================== 9. downstream/up ====
{
  const s = newSlide(
    '[appendix] Two challenge conversations, and they are completely independent.\n' +
    'Downstream — proving to me, on the LAN — is http-01 or tls-alpn-01, so a box that only speaks TLS is fine.\n' +
    'Upstream — proving to Let\'s Encrypt — is DNS-01 by default, or edge http-01 if you are actually publicly reachable.'
  )
  title(s, 'Two challenges, two directions')
  card(s, {
    x: 0.65, y: 1.55, w: 5.9, h: 4.0, eyebrow: 'DOWNSTREAM  ·  PROVE IT TO ME', eyebrowColor: VIOLET_MID,
    head: 'http-01\ntls-alpn-01', headMono: true, headSize: 26, headH: 1.15, headColor: INK,
    body: 'Port 80 if the box has a web server.\n\nRFC 8737 over port 443 if it does not — the challenge rides in the TLS handshake itself.\n\nWhichever listener the appliance already has.',
  })
  card(s, {
    x: 6.78, y: 1.55, w: 5.9, h: 4.0, eyebrow: 'UPSTREAM  ·  PROVE IT TO THEM', eyebrowColor: ACCENT,
    head: 'dns-01\nhttp-01 at the edge', headMono: true, headSize: 26, headH: 1.15, headColor: INK,
    body: 'dns-01 (default): nothing needs to be publicly reachable. Ever.\n\nedge http-01: faster than DNS propagation, but you need a public IP and a wildcard A record.\n\nOne env var switches it.',
  })
  kicker(s, '# appendix · ACME_LAN_UPSTREAM_CHALLENGE=dns-01')
}

await pres.writeFile({ fileName: OUT })
console.log('wrote', OUT)
