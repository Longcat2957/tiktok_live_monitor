import { defineConfig } from '@playwright/test';

export default defineConfig({
    testDir: './e2e',
    fullyParallel: false,
    forbidOnly: Boolean(process.env.CI),
    reporter: process.env.CI ? [['line'], ['html', { open: 'never' }]] : 'list',
    workers: 1,
    timeout: 45000,
    use: {
        baseURL: 'http://127.0.0.1:18765',
        browserName: 'chromium',
        headless: true,
        launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
            ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
            : {},
        screenshot: 'only-on-failure',
        trace: process.env.CI ? 'retain-on-failure' : 'off',
    },
});
