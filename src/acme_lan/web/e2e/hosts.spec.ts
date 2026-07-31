import { expect, test } from '@playwright/test'

test.describe('managed hosts', () => {
  test('shows the seeded host', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Managed hosts' })).toBeVisible()
    await expect(page.getByRole('cell', { name: 'printer01', exact: true })).toBeVisible()
  })

  test('warns when choosing the local CSR source in the modal', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: '+ Add host' }).click()
    const modal = page.getByTestId('host-modal')
    await expect(modal).toBeVisible()

    await modal.getByTestId('csr-source-select').selectOption('local')
    await expect(modal.getByText(/generates and stores the private key/i)).toBeVisible()
    // Switching back to device hides the warning.
    await modal.getByTestId('csr-source-select').selectOption('device')
    await expect(modal.getByText(/generates and stores the private key/i)).toHaveCount(0)
  })

  test('renders plugin-specific config fields that change with plugin/mode', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: '+ Add host' }).click()
    const modal = page.getByTestId('host-modal')

    // local plugin, device mode → csr_path is the device field.
    await modal.getByTestId('plugin-select').selectOption('local')
    await modal.getByTestId('csr-source-select').selectOption('device')
    await expect(modal.getByPlaceholder('/etc/ssl/app.csr')).toBeVisible()

    // switching to local mode swaps in the key path field.
    await modal.getByTestId('csr-source-select').selectOption('local')
    await expect(modal.getByPlaceholder('/etc/ssl/app.key')).toBeVisible()

    // switching plugin swaps in that plugin's fields.
    await modal.getByTestId('plugin-select').selectOption('ssh')
    await expect(modal.getByPlaceholder('/etc/ssl/device.crt')).toBeVisible()
  })

  test('can add, edit and delete a host via the modal', async ({ page }) => {
    await page.goto('/')

    // Add.
    await page.getByRole('button', { name: '+ Add host' }).click()
    const modal = page.getByTestId('host-modal')
    await modal.getByPlaceholder('esxi01', { exact: true }).fill('esxi-e2e')
    await modal.getByPlaceholder('esxi01.lan').fill('esxi-e2e.lan.test')
    await modal.getByPlaceholder('192.168.3.5').fill('192.168.3.50')
    await modal.getByTestId('plugin-select').selectOption('local')
    await modal.getByTestId('csr-source-select').selectOption('local')
    await modal.getByPlaceholder('/etc/ssl/app.crt').fill('/tmp/c')
    await modal.getByPlaceholder('/etc/ssl/app.key').fill('/tmp/k')
    await modal.getByRole('button', { name: 'Add host' }).click()

    const row = page.locator('tr', { hasText: 'esxi-e2e' })
    await expect(row).toBeVisible()

    // Edit: modal pre-fills the existing values.
    await row.getByRole('button', { name: 'edit' }).click()
    const editModal = page.getByTestId('host-modal')
    await expect(editModal.getByRole('heading', { name: 'Edit host' })).toBeVisible()
    await expect(editModal.getByPlaceholder('192.168.3.5')).toHaveValue('192.168.3.50')
    await editModal.getByPlaceholder('192.168.3.5').fill('192.168.3.51')
    await editModal.getByRole('button', { name: 'Save changes' }).click()
    await expect(page.getByRole('cell', { name: '192.168.3.51:443' })).toBeVisible()

    // Delete.
    await page.locator('tr', { hasText: 'esxi-e2e' }).getByRole('button', { name: 'delete' }).click()
    await expect(page.getByText('esxi-e2e', { exact: true })).toHaveCount(0)
  })
})
