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
  await page.getByLabel('Токен станции', { exact: true }).fill(tokens.station)
  await page.getByRole('button', { name: 'Подключить', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await page.getByRole('button', { name: /Планирование проекта · учебный пример/ }).click()
  await expect(page.getByRole('heading', { name: 'Планирование проекта · учебный пример', exact: true })).toBeVisible()
  await expect(page.getByText('Учебный пример: данные подготовлены для проверки интерфейса. Распознавание речи и ИИ-извлечение не запускались.')).toBeVisible()
  await page.getByRole('button', { name: 'Проверить и исправить' }).click()
  await page.getByLabel('Кто проверяет').fill('Acceptance test secretary')
  await page.getByLabel(/Участник 1/).fill('Айдана')
  await page.getByLabel(/Участник 2/).fill('Бекзат')
  await page.getByLabel('Ответственный', { exact: true }).fill('Тимур')
  await page.getByLabel('Подтверждённая дата', { exact: true }).fill('2026-09-28')
  await page.getByLabel('Срок в исходной реплике').fill('к понедельнику')
  await page.getByLabel('Результат проверки').selectOption('human_confirmed')
  await page.getByRole('button', { name: 'Сохранить проверку', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Проверка протокола', exact: true })).toBeHidden()
  await expect(page.getByText('История проверки · версия 1')).toBeVisible()
  await expect(page.locator('.mi-action-table')).toContainText('Тимур')
  await expect(page.locator('.mi-action-table')).toContainText('2026-09-28')
  await page.getByRole('tab', { name: /Расшифровка/ }).click()
  await expect(page.locator('.mi-segment .mi-speaker').first()).toHaveText('Айдана')
  await expect(page.locator('.mi-segment .mi-speaker').nth(1)).toHaveText('Бекзат')
  await page.getByRole('tab', { name: 'Протокол', exact: true }).click()
  for (const format of ['docx', 'pdf']) {
    await page.getByLabel('Формат экспорта').selectOption(format)
    const downloading = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Скачать', exact: true }).click()
    const download = await downloading
    expect(await download.failure()).toBeNull()
    await download.saveAs(path.join(process.env.MI_UI_ARTIFACTS, 'review.' + format))
  }
  await page.reload()
  await expect(page.getByText('История проверки · версия 1')).toBeVisible()
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
  await page.getByLabel('Токен станции', { exact: true }).fill(tokens.station)
  await page.getByRole('button', { name: 'Подключить', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await page.getByRole('button', { name: /Без извлечённых поручений · учебный пример/ }).click()
  await expect(page.getByText('Поручения и решения не извлечены. Проверьте расшифровку и исходную запись перед использованием протокола.')).toBeVisible()
  await page.getByRole('button', { name: 'Проверить и исправить' }).click()
  await page.getByLabel('Кто проверяет').fill('Missed-action acceptance secretary')
  await page.getByRole('button', { name: 'Добавить пропущенное поручение', exact: true }).click()
  await page.getByRole('button', { name: 'Удалить пропущенное поручение 1', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Сохранить проверку', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Добавить пропущенное поручение', exact: true }).click()
  await page.getByLabel('Суть пропущенного поручения', { exact: true }).fill('Подготовить отчёт')
  await page.getByLabel('Ответственный за пропущенное поручение', { exact: true }).fill('Тимур')
  await page.getByLabel('Дата пропущенного поручения', { exact: true }).fill('2026-09-28')
  await page.getByLabel('Исходный срок пропущенного поручения').fill('к понедельнику')
  await expect(page.getByRole('button', { name: 'Сохранить проверку', exact: true })).toBeDisabled()
  await page.getByLabel('Исходные реплики').selectOption('s2')
  await expect(page.getByRole('button', { name: 'Сохранить проверку', exact: true })).toBeDisabled()
  await expect(page.locator('.mi-review-card blockquote')).toHaveText('Уточнение: отчёт подготовит Тимур к понедельнику.')
  await page.getByLabel('Проверка пропущенного поручения').selectOption('human_confirmed')
  const saving = page.waitForResponse(response => response.url().endsWith('/review') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Сохранить проверку', exact: true }).click()
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
  await expect(page.getByText('История проверки · версия 1')).toBeVisible()
  await expect(page.locator('.mi-action-table')).toContainText('Тимур')
  for (const format of ['docx', 'pdf']) {
    await page.getByLabel('Формат экспорта').selectOption(format)
    const downloading = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Скачать', exact: true }).click()
    const download = await downloading
    expect(await download.failure()).toBeNull()
    await download.saveAs(path.join(process.env.MI_UI_ARTIFACTS, 'missed-action.' + format))
  }
  await page.reload()
  await expect(page.locator('.mi-action-table')).toContainText('Тимур')
  await expect(page.getByText('История проверки · версия 1')).toBeVisible()
  expect(errors).toEqual([])
  expect(external).toEqual([])
})
