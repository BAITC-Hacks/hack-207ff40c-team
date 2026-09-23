import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '.', testMatch: 'review.spec.ts', timeout: 60000, workers: 1,
  reporter: 'list', outputDir: '../../../.local/playwright-results',
  use: { baseURL: process.env.MI_UI_BASE_URL, browserName: 'chromium', headless: true, viewport: { width: 1440, height: 1000 } },
})
