import { expect, test } from '@playwright/test'

test.describe('managed hosts', () => {
  test('shows the seeded host', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Managed hosts' })).toBeVisible()
    await expect(page.getByRole('cell', { name: 'printer01', exact: true })).toBeVisible()
  })

  test('warns when choosing the local CSR source', async ({ page }) => {
    await page.goto('/')
    await page.locator('select').selectOption('local')
    await expect(page.getByText(/generates and stores the private key/i)).toBeVisible()
    // Switching back to device hides the warning.
    await page.locator('select').selectOption('device')
    await expect(page.getByText(/generates and stores the private key/i)).toHaveCount(0)
  })

  test('can add and delete a host', async ({ page }) => {
    await page.goto('/')
    await page.getByPlaceholder('esxi01', { exact: true }).fill('esxi-e2e')
    await page.getByPlaceholder('esxi01.lan').fill('esxi-e2e.lan.test')
    await page.getByPlaceholder('192.168.3.5').fill('192.168.3.50')
    await page.locator('select').selectOption('local')
    await page.getByPlaceholder(/cert_path/).fill('{"cert_path":"/tmp/c","key_path":"/tmp/k"}')
    await page.getByRole('button', { name: 'Add host' }).click()

    const row = page.locator('tr', { hasText: 'esxi-e2e' })
    await expect(row).toBeVisible()

    await row.getByRole('button', { name: 'delete' }).click()
    await expect(page.getByText('esxi-e2e', { exact: true })).toHaveCount(0)
  })
})
