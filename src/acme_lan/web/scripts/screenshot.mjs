// Capture dashboard screenshots for the docs. Assumes the rich screenshot server is
// running (tests/screenshot_server.py) on the given base URL.
//
//   uv run python tests/screenshot_server.py &   # port 8124
//   node src/acme_lan/web/scripts/screenshot.mjs
//
// Set ACME_LAN_PW_CHROMIUM to reuse a pre-installed Chromium if needed.
import { chromium } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(dirname, '../../../..')
const outDir = path.join(repoRoot, 'docs', 'img')
const baseURL = process.env.SHOT_BASE_URL || 'http://127.0.0.1:8124'

const browser = await chromium.launch({
  executablePath: process.env.ACME_LAN_PW_CHROMIUM || undefined,
})
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 })
await page.goto(baseURL, { waitUntil: 'networkidle' })
// Give the realtime health probes a moment to resolve.
await page.waitForTimeout(2500)

await page.screenshot({ path: path.join(outDir, 'dashboard.png'), fullPage: true })
console.log('wrote docs/img/dashboard.png')

// The "add host" modal, with an SSH plugin selected so its schema-driven config fields show.
// Managed hosts live behind their own tab in the dashboard shell.
await page.getByTestId('tab-hosts').click()
await page.getByRole('button', { name: '+ Add host' }).click()
const modal = page.getByTestId('host-modal')
// Selects are Catalyst listboxes, not native <select>s: click the button, then the option
// (which renders in a portal at the document root, hence the page-level lookup).
await modal.getByTestId('plugin-select').click()
await page.getByRole('option', { name: 'ssh', exact: true }).click()
await modal.getByPlaceholder('esxi01', { exact: true }).fill('esxi01')
await modal.getByPlaceholder('esxi01.lan').fill('esxi01.lan')
await modal.getByPlaceholder('192.168.3.5').fill('192.168.3.5')
await page.waitForTimeout(300)

// Drop focus so the last-filled field doesn't carry a focus ring into the shot.
await page.evaluate(() => document.activeElement?.blur())

// The panel is taller than the default viewport and sits in a fixed, scrolling container,
// which clips an element screenshot — grow the viewport to the whole panel first.
const box = await modal.boundingBox()
await page.setViewportSize({ width: 1280, height: Math.ceil(box.height) + 64 })
await page.waitForTimeout(300)
await modal.screenshot({ path: path.join(outDir, 'add-host-modal.png') })
console.log('wrote docs/img/add-host-modal.png')

await browser.close()
