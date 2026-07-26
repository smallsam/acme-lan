import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig, devices } from '@playwright/test'

const PORT = 8123
const dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(dirname, '../../..')

// The dashboard is served by the acme-lan backend (tests/ui_server.py) against a seeded
// database, so these tests exercise the real built SPA + real management API.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Optional override for environments with a pre-installed Chromium (unset in CI,
        // where `playwright install` provides the matching browser).
        launchOptions: process.env.ACME_LAN_PW_CHROMIUM
          ? { executablePath: process.env.ACME_LAN_PW_CHROMIUM }
          : {},
      },
    },
  ],
  webServer: {
    command: 'uv run python tests/ui_server.py',
    cwd: repoRoot,
    url: `http://127.0.0.1:${PORT}/healthz`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: { ACME_LAN_UI_PORT: String(PORT) },
  },
})
