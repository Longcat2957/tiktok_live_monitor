import { spawn, type ChildProcess } from 'node:child_process';
import { once } from 'node:events';
import { resolve } from 'node:path';
import { expect, test, type Locator, type Page } from '@playwright/test';

const baseURL = 'http://127.0.0.1:18768';
test.use({ baseURL });
let server: ChildProcess | undefined;

test.beforeAll(async () => {
  server = spawn(resolve('../backend/.venv/bin/python'), ['-m', 'uvicorn', 'app.main:app',
    '--host', '127.0.0.1', '--port', '18768', '--ws', 'websockets-sansio'], {
    cwd: resolve('../backend'),
    env: { ...process.env, COMMENT_SOURCE: 'mock', MOCK_INTERVAL_SECONDS: '0.1',
      COMMENT_HISTORY_SIZE: '30', STATIC_DIR: resolve('build') },
    stdio: 'pipe'
  });
  let logs = '';
  server.stderr?.on('data', chunk => { logs = (logs + chunk.toString()).slice(-4000); });
  await expect.poll(async () => {
    if (server?.exitCode !== null) throw new Error(logs);
    try { return (await fetch(`${baseURL}/health`)).ok; } catch { return false; }
  }, { timeout: 10000 }).toBe(true);
});

test.afterAll(async () => {
  if (server && server.exitCode === null) {
    const exited = once(server, 'exit');
    server.kill('SIGTERM');
    await exited;
  }
});

test.beforeEach(async ({ request }) => {
  const { session_id } = await (await request.get('/config')).json();
  expect((await request.delete('/account', { data: { session_id } })).ok()).toBe(true);
});

async function tabTo(page: Page, target: Locator) {
  for (let attempt = 0; attempt < 12; attempt++) {
    if (await target.evaluate(node => node === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  await expect(target).toBeFocused();
}

async function expectNoHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => {
    const selectors = 'main, header, .account-panel, .account-panel form, .monitor-actions, .live-summary, footer, dialog[open]';
    return document.documentElement.scrollWidth <= innerWidth &&
      [...document.querySelectorAll<HTMLElement>(selectors)].every(node => {
        const bounds = node.getBoundingClientRect();
        return bounds.left >= -1 && bounds.right <= innerWidth + 1 && node.scrollWidth <= node.clientWidth + 1;
      });
  })).toBe(true);
}

test('setup theme can be changed with the keyboard and survives reload', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: '시작', exact: true })).toBeEnabled();
  const light = page.getByRole('button', { name: '라이트 테마로 전환' });
  await tabTo(page, light);
  await page.keyboard.press('Enter');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  expect(await page.evaluate(() => localStorage.getItem('monitor-theme'))).toBe('light');
  await page.reload();
  await expect(page.getByRole('button', { name: '다크 테마로 전환' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

for (const width of [390, 320]) {
  test(`setup, monitor and keyboard-operated settings fit a ${width}px screen`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/');
    await expect(page.getByRole('button', { name: '시작', exact: true })).toBeEnabled();
    await expectNoHorizontalOverflow(page);
    await page.getByText('실제 방송', { exact: true }).click();
    await expect(page.getByLabel('TikTok 아이디 또는 방송 주소')).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await page.getByText('데모 체험', { exact: true }).first().click();
    await page.getByRole('button', { name: '시작', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('.comment').first()).toBeVisible();
    await expect(page.locator('#monitor-title')).toBeFocused();
    await expectNoHorizontalOverflow(page);

    const settings = page.getByRole('button', { name: '모니터 설정' });
    await tabTo(page, settings);
    await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog', { name: '데모 설정' });
    await expect(dialog.getByLabel('목록 보관 수')).toBeEnabled();
    await expectNoHorizontalOverflow(page);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(settings).toBeFocused();

    await tabTo(page, page.getByRole('button', { name: '모니터 종료 · 처음으로' }));
    await page.keyboard.press('Enter');
    await expect(page.getByRole('radio', { name: '데모 체험' })).toBeFocused();
    expect(errors).toEqual([]);
  });
}

test('invalid input in collapsed advanced settings is revealed and focused', async ({ page }) => {
  const updates: string[] = [];
  page.on('request', request => {
    if (request.method() === 'PATCH' && request.url().endsWith('/config')) updates.push(request.url());
  });
  await page.goto('/');
  await page.getByRole('button', { name: '시작', exact: true }).click();
  await page.getByRole('button', { name: '모니터 설정' }).click();
  const dialog = page.getByRole('dialog', { name: '데모 설정' });
  await expect(dialog.getByLabel('목록 보관 수')).toBeEnabled();
  const advanced = dialog.locator('details');
  const summary = advanced.locator('summary');
  await expect(advanced).not.toHaveAttribute('open');
  await summary.focus();
  await page.keyboard.press('Enter');
  const queue = dialog.getByLabel('수신 대기 큐 크기');
  await queue.fill('0');
  await summary.click();
  await expect(queue).toBeHidden();
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(advanced).toHaveAttribute('open');
  await expect(queue).toBeFocused();
  await expect(dialog.getByRole('alert')).toContainText('허용 범위');
  expect(updates).toEqual([]);
  await queue.fill('50');
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(dialog).toBeHidden();
  expect(updates).toHaveLength(1);
});
