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
await page.getByRole('button', { name: '+ Add host' }).click()
const modal = page.getByTestId('host-modal')
await modal.getByTestId('plugin-select').selectOption('ssh')
await modal.getByPlaceholder('esxi01', { exact: true }).fill('esxi01')
await modal.getByPlaceholder('esxi01.lan').fill('esxi01.lan')
await modal.getByPlaceholder('192.168.3.5').fill('192.168.3.5')
await page.waitForTimeout(300)
await modal.screenshot({ path: path.join(outDir, 'add-host-modal.png') })
console.log('wrote docs/img/add-host-modal.png')

await browser.close()
