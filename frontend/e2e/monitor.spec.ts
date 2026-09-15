import { spawn, type ChildProcess } from 'node:child_process';
import { once } from 'node:events';
import { resolve } from 'node:path';
import { expect, test } from '@playwright/test';

let server: ChildProcess | undefined;
async function startServer() {
  server = spawn(resolve('../backend/.venv/bin/python'), ['-m', 'uvicorn', 'app.main:app',
    '--host', '127.0.0.1', '--port', '18765', '--ws', 'websockets-sansio'], {
    cwd: resolve('../backend'),
    env: { ...process.env, COMMENT_SOURCE: 'mock', MOCK_INTERVAL_SECONDS: '0.04', COMMENT_HISTORY_SIZE: '30' },
    stdio: 'pipe'
  });
  let logs = '';
  server.stderr?.on('data', (chunk) => { logs = (logs + chunk.toString()).slice(-4000); });
  await expect.poll(async () => {
    if (server?.exitCode !== null) throw new Error(logs);
    try { return (await fetch('http://127.0.0.1:18765/health')).ok; } catch { return false; }
  }, { timeout: 10000 }).toBe(true);
}
async function stopServer() {
  if (server && server.exitCode === null) {
    const exited = once(server, 'exit');
    server.kill('SIGTERM');
    await exited;
  }
}
test.beforeAll(startServer);
test.afterAll(stopServer);

for (const viewport of [{ width: 1080, height: 1920 }, { width: 720, height: 1280 }]) {
  test(`mock comments fit ${viewport.width}×${viewport.height} and remain bounded`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('dialog', () => errors.push('Unexpected script execution'));
    await page.setViewportSize(viewport);
    await page.goto('/');
    await expect(page.locator('.comment')).toHaveCount(30);
    await expect(page.locator('.connection')).toHaveAttribute('data-state', 'connected');
    await expect(page.locator('.body').filter({ hasText: '<script>' }).first()).toBeAttached();
    await page.waitForTimeout(1600);
    expect(await page.locator('.comment').count()).toBe(30);
    expect(await page.evaluate(() => {
      const scroll = document.querySelector('.comment-viewport')!;
      const footer = document.querySelector('footer')!.getBoundingClientRect();
      const last = document.querySelector('.comment:last-child')!.getBoundingClientRect();
      return document.documentElement.scrollWidth <= innerWidth && scroll.scrollWidth <= scroll.clientWidth && last.bottom <= footer.top;
    })).toBe(true);
    expect(errors).toEqual([]);
    await page.screenshot({ path: `test-results/monitor-${viewport.width}.png` });
  });
}

test('backend restart reconnects without reload and keeps existing comments', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.comment')).toHaveCount(30);
  await stopServer();
  await expect(page.locator('.connection')).toHaveAttribute('data-state', /disconnected|connecting/);
  const previous = await page.locator('.comment').last().getAttribute('data-comment-id');
  await page.waitForTimeout(500);
  expect(await page.locator('.comment').last().getAttribute('data-comment-id')).toBe(previous);
  await startServer();
  await expect(page.locator('.connection')).toHaveAttribute('data-state', 'connected', { timeout: 12000 });
  await expect(page.locator('.comment').last()).not.toHaveAttribute('data-comment-id', previous!);
});

test('malformed frames are ignored and burst comments preserve order', async ({ page }) => {
  await page.routeWebSocket('**/ws', (socket) => {
    socket.send('{broken');
    socket.send(JSON.stringify({ type: 'status', state: 'unknown' }));
    for (let i = 0; i < 1000; i++) {
      socket.send(JSON.stringify({ type: 'comment', id: String(i), received_at: new Date().toISOString(),
        user: { nickname: '', unique_id: 'fallback-id' }, comment: `댓글 ${i} ${'a'.repeat(500)}` }));
    }
  });
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('.comment')).toHaveCount(30);
  await expect(page.locator('.comment').first()).toHaveAttribute('data-comment-id', '970');
  await expect(page.locator('.comment').last()).toHaveAttribute('data-comment-id', '999');
  await expect(page.locator('.nickname').last()).toHaveText('fallback-id');
  expect(errors).toEqual([]);
});
