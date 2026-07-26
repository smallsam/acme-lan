import { expect, test } from '@playwright/test'

test.describe('dashboard', () => {
  test('renders the header and seeded stats', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'acme-lan' })).toBeVisible()
    // One certificate was seeded.
    await expect(page.getByTestId('stat-certificates')).toHaveText('1')
  })

  test('lists the seeded certificate with a live health badge', async ({ page }) => {
    await page.goto('/')
    const row = page.locator('tr', { hasText: 'db.lan.test' })
    await expect(row).toBeVisible()
    // A realtime health badge renders (…, unreachable, expired, or "Nd left").
    await expect(row.locator('span').first()).toBeVisible()
    await expect(row.getByRole('button', { name: 're-check' })).toBeVisible()
  })

  test('ad-hoc TLS probe returns a result for a closed port', async ({ page }) => {
    await page.goto('/')
    await page.getByPlaceholder('ldap.lan').fill('127.0.0.1')
    await page.locator('input[type=number]').fill('1') // nothing listening
    await page.getByRole('button', { name: 'Probe' }).click()

    const result = page.locator('pre')
    await expect(result).toBeVisible()
    await expect(result).toContainText('"reachable": false')
  })
})
