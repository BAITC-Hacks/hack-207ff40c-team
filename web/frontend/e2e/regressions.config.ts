import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '.', testMatch: 'regressions.spec.ts', timeout: 30000, workers: 1,
  reporter: 'list', outputDir: '../../../.local/frontend-regressions',
  use: {
    baseURL: 'http://127.0.0.1:4174', browserName: 'chromium', headless: true,
    viewport: { width: 1440, height: 1000 }, permissions: ['microphone'],
    launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 4174 --strictPort',
    cwd: new URL('..', import.meta.url).pathname,
    env: { VITE_MEETING_STATION: 'true', VITE_MEETING_LOCAL: 'true' },
    url: 'http://127.0.0.1:4174/e2e/regression.html', reuseExistingServer: false,
  },
})
