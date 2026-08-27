# acme-lan — PyCon AU 2026 lightning talk

A five-minute lightning talk on why acme-lan exists, how it works, what else you could
use instead, and how it chains to [acme-dns](https://github.com/joohoi/acme-dns).

| File | What it is |
| --- | --- |
| `acme-lan-pycon-au-2026.pptx` | The deck. Editable in PowerPoint, Keynote, or Google Slides (File → Import slides). |
| `acme-lan-pycon-au-2026.pdf` | Same deck, for presenting off a USB stick when the venue laptop hates you. |
| `NOTES.md` | Run sheet: per-slide timings and the spoken script (also in the deck's speaker notes). |
| `build_deck.mjs` | Generator, if you'd rather edit the source than the slides. |
| `img/` | Screenshots, captured from the current build. |

## Rebuilding

```bash
npm install pptxgenjs
node talks/pycon-au-2026/build_deck.mjs
```

## Recapturing the screenshots

The shots come from the seeded documentation server, so the dashboard has live health
badges, an expiring device cert, and a cert linked to a managed host:

```bash
uv run python tests/screenshot_server.py &        # port 8124
node src/acme_lan/web/scripts/screenshot.mjs      # dashboard + add-host modal
```

`certs-table.png`, `hosts-table.png` and `probe.png` are section crops of the same page.
The probe result is a real handshake against a throwaway local TLS endpoint.

## Colours

PyCon AU / Python palette: deep navy `071A2F`, Python blue `4B8BBE`, Python yellow
`FFD43B` as the accent, with `3DDC97` / `FF7A7A` for good and bad news. Swap the constants
at the top of `build_deck.mjs` if the 2026 brand kit says otherwise.
