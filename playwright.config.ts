import { defineConfig, devices } from '@playwright/test';

const origin = 'http://127.0.0.1:4173';

export default defineConfig({
  testDir: './tests',
  use: { baseURL: origin },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'android-emulation', use: { ...devices['Pixel 7'] } },
    { name: 'iphone-emulation', use: { ...devices['iPhone 13'] } },
  ],
  webServer: {
    command: 'node tests/browser-server.mjs',
    url: origin,
    env: { VITE_API_BASE_URL: origin },
  },
});
