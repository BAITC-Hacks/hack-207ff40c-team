import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

test('secretary identifies speakers, corrects an action and downloads the saved revision', async ({ page }) => {
  if (!process.env.MI_UI_BASE_URL || !process.env.MI_UI_STATE_DIR || !process.env.MI_UI_ARTIFACTS) throw new Error('Run through scripts/check-ui.py to isolate the synthetic archive')
  const tokens = JSON.parse(await readFile(path.join(process.env.MI_UI_STATE_DIR, 'tokens.json'), 'utf8'))
  const external: string[] = []
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/*', route => {
    const target = new URL(route.request().url())
    if (target.protocol === 'http:' || target.protocol === 'https:') {
      if (target.origin !== new URL(process.env.MI_UI_BASE_URL!).origin) {
        external.push(target.origin); return route.abort()
      }
    }
    return route.continue()
  })
  await page.goto('/meeting-intelligence')
  await page.getByLabel('Station token', { exact: true }).fill(tokens.station)
  await page.getByRole('button', { name: 'Connect', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await page.getByRole('button', { name: /Synthetic acceptance fixture · RU\/KZ/ }).click()
  await expect(page.getByRole('heading', { name: 'Synthetic acceptance fixture · RU/KZ', exact: true })).toBeVisible()
  await expect(page.getByText('Synthetic acceptance fixture. Speech recognition and AI extraction were not run.')).toBeVisible()
  await page.getByRole('button', { name: 'Review & correct' }).click()
  await page.getByLabel('Reviewer name').fill('Acceptance test secretary')
  await page.getByLabel(/Speaker 1/).fill('Айдана')
  await page.getByLabel(/Speaker 2/).fill('Бекзат')
  await page.getByLabel('Owner', { exact: true }).fill('Тимур')
  await page.getByLabel('Agreed date', { exact: true }).fill('2026-09-28')
  await page.getByLabel('Deadline as spoken').fill('к понедельнику')
  await page.getByLabel('Review decision').selectOption('human_confirmed')
  await page.getByRole('button', { name: 'Save review', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Review the meeting', exact: true })).toBeHidden()
  await expect(page.getByText('Review history · revision 1')).toBeVisible()
  await expect(page.locator('.mi-action-table')).toContainText('Тимур')
  await expect(page.locator('.mi-action-table')).toContainText('2026-09-28')
  await page.getByRole('tab', { name: /Transcript/ }).click()
  await expect(page.locator('.mi-segment .mi-speaker').first()).toHaveText('Айдана')
  await expect(page.locator('.mi-segment .mi-speaker').nth(1)).toHaveText('Бекзат')
  await page.getByRole('tab', { name: 'Overview', exact: true }).click()
  for (const format of ['docx', 'pdf']) {
    await page.getByLabel('Export format').selectOption(format)
    const downloading = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Export', exact: true }).click()
    const download = await downloading
    expect(await download.failure()).toBeNull()
    await download.saveAs(path.join(process.env.MI_UI_ARTIFACTS, 'review.' + format))
  }
  await page.reload()
  await expect(page.getByText('Review history · revision 1')).toBeVisible()
  await expect(page.locator('.mi-action-table')).toContainText('Тимур')
  await page.screenshot({ path: path.join(process.env.MI_UI_ARTIFACTS, 'review-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: path.join(process.env.MI_UI_ARTIFACTS, 'review-mobile.png'), fullPage: true })
  expect(external).toEqual([])
  expect(errors).toEqual([])
})

test('secretary recovers an omitted action from an empty report with an immutable source excerpt', async ({ page }) => {
  if (!process.env.MI_UI_BASE_URL || !process.env.MI_UI_STATE_DIR || !process.env.MI_UI_ARTIFACTS) throw new Error('Run through scripts/check-ui.py')
  const tokens = JSON.parse(await readFile(path.join(process.env.MI_UI_STATE_DIR, 'tokens.json'), 'utf8'))
  const errors: string[] = []
  const external: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/*', route => {
    const target = new URL(route.request().url())
    if (['http:', 'https:'].includes(target.protocol) && target.origin !== new URL(process.env.MI_UI_BASE_URL!).origin) {
      external.push(target.origin); return route.abort()
    }
    return route.continue()
  })
  await page.goto('/meeting-intelligence')
  await page.getByLabel('Station token', { exact: true }).fill(tokens.station)
  await page.getByRole('button', { name: 'Connect', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await page.getByRole('button', { name: /Synthetic empty extraction · RU\/KZ/ }).click()
  await expect(page.getByText('No structured meeting findings were extracted. Check the transcript and original recording before relying on this report.')).toBeVisible()
  await page.getByRole('button', { name: 'Review & correct' }).click()
  await page.getByLabel('Reviewer name').fill('Missed-action acceptance secretary')
  await page.getByRole('button', { name: 'Add missed action', exact: true }).click()
  await page.getByRole('button', { name: 'Remove missed action 1', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Save review', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Add missed action', exact: true }).click()
  await page.getByLabel('Missed task', { exact: true }).fill('Подготовить отчёт')
  await page.getByLabel('Missed action owner', { exact: true }).fill('Тимур')
  await page.getByLabel('Missed action date', { exact: true }).fill('2026-09-28')
  await page.getByLabel('Missed action deadline as spoken').fill('к понедельнику')
  await expect(page.getByRole('button', { name: 'Save review', exact: true })).toBeDisabled()
  await page.getByLabel('Source passages').selectOption('s2')
  await expect(page.getByRole('button', { name: 'Save review', exact: true })).toBeDisabled()
  await expect(page.locator('.mi-review-card blockquote')).toHaveText('Уточнение: отчёт подготовит Тимур к понедельнику.')
  await page.getByLabel('Missed action review decision').selectOption('human_confirmed')
  const saving = page.waitForResponse(response => response.url().endsWith('/review') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Save review', exact: true }).click()
  const response = await saving
  expect(response.status()).toBe(200)
  const saved = await response.json()
  expect(saved.protocol.action_items).toHaveLength(1)
  expect(saved.protocol.action_items[0]).toMatchObject({ assignee: 'Тимур', source_check: 'unavailable', review_status: 'human_confirmed', evidence: { segment_ids: ['s2'], quote: 'Уточнение: отчёт подготовит Тимур к понедельнику.' } })
  expect(saved.review_history[0].changes[0].before).toBeNull()
  const replay = await page.request.post(response.url(), { headers: { Authorization: `Bearer ${tokens.station}` }, data: response.request().postDataJSON() })
  expect(replay.status()).toBe(200)
  const repeated = await replay.json()
  expect(repeated.review_revision).toBe(1)
  expect(repeated.protocol.action_items).toHaveLength(1)
  await expect(page.getByText('Review history · revision 1')).toBeVisible()
  await expect(page.locator('.mi-action-table')).toContainText('Тимур')
  for (const format of ['docx', 'pdf']) {
    await page.getByLabel('Export format').selectOption(format)
    const downloading = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Export', exact: true }).click()
    const download = await downloading
    expect(await download.failure()).toBeNull()
    await download.saveAs(path.join(process.env.MI_UI_ARTIFACTS, 'missed-action.' + format))
  }
  await page.reload()
  await expect(page.locator('.mi-action-table')).toContainText('Тимур')
  await expect(page.getByText('Review history · revision 1')).toBeVisible()
  expect(errors).toEqual([])
  expect(external).toEqual([])
})
