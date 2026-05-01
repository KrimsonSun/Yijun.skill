import { defineConfig, devices } from '@playwright/test';

const EMMA_URL = process.env.EMMA_URL || 'http://localhost:5173';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,         // chat is stateful — one fixture at a time
  retries: 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/results.json' }],
  ],
  use: {
    baseURL: EMMA_URL,
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } },
    },
  ],
});
