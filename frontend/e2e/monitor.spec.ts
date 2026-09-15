import { spawn, type ChildProcess } from 'node:child_process';
import { once } from 'node:events';
import { resolve } from 'node:path';
import { expect, test, type APIRequestContext } from '@playwright/test';

async function change(request: APIRequestContext, method: string, path: string, body = {}) {
  const { session_id } = await (await request.get('/config')).json();
  const response = await request.fetch(path, { method, data: { session_id, ...body } });
  expect(response.ok()).toBe(true);
  return response;
}
async function startMock(request: APIRequestContext) {
  await change(request, 'DELETE', '/account');
  await change(request, 'POST', '/account', { source: 'mock' });
}

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
  test(`mock comments fit ${viewport.width}×${viewport.height} and remain bounded`, async ({ page, request }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('dialog', () => errors.push('Unexpected script execution'));
    await page.setViewportSize(viewport);
    await change(request, 'DELETE', '/account');
    await page.goto('/');
    if (viewport.width === 1080) {
      await expect(page.getByRole('radio', { name: '데모 체험' })).toBeChecked();
      await expect(page.locator('.comment')).toHaveCount(0);
      await page.screenshot({ path: 'test-results/mode-selection.png' });
      // M3 hides the native radios visually; keyboard selection must still work.
      await page.keyboard.press('Tab');
      await expect(page.getByRole('button', { name: '라이트 테마로 전환' })).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(page.getByRole('radio', { name: '데모 체험' })).toBeFocused();
      await page.keyboard.press('ArrowLeft');
      await expect(page.getByRole('radio', { name: '실제 방송' })).toBeChecked();
      const start = await page.getByRole('button', { name: '시작', exact: true }).boundingBox();
      expect(start!.height).toBeGreaterThanOrEqual(44);
    }
    await page.getByText('실제 방송', { exact: true }).click();
    await expect(page.getByLabel('TikTok 아이디 또는 방송 주소')).toBeVisible();
    const formBefore = await page.locator('.account-panel form').boundingBox();
    const startBefore = await page.getByRole('button', { name: '시작', exact: true }).boundingBox();
    await page.getByText('데모 체험', { exact: true }).first().click();
    await expect(page.getByLabel('TikTok 아이디 또는 방송 주소')).toBeHidden();
    expect(await page.locator('.account-panel form').boundingBox()).toEqual(formBefore);
    expect(await page.getByRole('button', { name: '시작', exact: true }).boundingBox()).toEqual(startBefore);
    await page.getByRole('button', { name: '시작', exact: true }).click();
    await expect(page.locator('.comment')).toHaveCount(30);
    await expect(page.locator('.connection')).toHaveAttribute('data-state', 'connected');
    if (viewport.width === 720) {
      const larger = page.getByRole('button', { name: '댓글 글자 크게' });
      const smaller = page.getByRole('button', { name: '댓글 글자 작게' });
      const fontSize = () => page.locator('[data-kind=comment] .body').last().evaluate(node => parseFloat(getComputedStyle(node).fontSize));
      const original = await fontSize();
      const session = (await (await request.get('/health')).json()).source.session_id;
      await larger.click();
      await expect.poll(fontSize).toBeCloseTo(original * 1.05, 1);
      for (let i = 0; i < 19; i++) await larger.click();
      await expect(larger).toBeDisabled();
      await expect.poll(fontSize).toBeCloseTo(original * 2, 1);
      await expect.poll(() => page.locator('.comment-viewport').evaluate(node =>
        Math.abs(node.scrollHeight - node.clientHeight - node.scrollTop)
      )).toBeLessThanOrEqual(1);
      for (let percent = 195; percent >= 20; percent -= 5) {
        await smaller.click();
        await expect.poll(fontSize).toBeCloseTo(original * percent / 100, 1);
      }
      await expect(smaller).toBeDisabled();
      await expect.poll(fontSize).toBeCloseTo(original * .2, 1);
      for (let percent = 25; percent <= 100; percent += 5) {
        await larger.click();
        await expect.poll(fontSize).toBeCloseTo(original * percent / 100, 1);
      }
      await expect.poll(fontSize).toBeCloseTo(original, 1);
      expect((await (await request.get('/health')).json()).source.session_id).toBe(session);
    }
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

test('backend restart returns to setup without reload and mock can start again', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.comment')).toHaveCount(30);
  await stopServer();
  await expect(page.locator('.connection')).toHaveAttribute('data-state', /disconnected|connecting/);
  const previous = await page.locator('.comment').last().getAttribute('data-comment-id');
  await page.waitForTimeout(500);
  expect(await page.locator('.comment').last().getAttribute('data-comment-id')).toBe(previous);
  await startServer();
  await expect(page.getByRole('group', { name: '실행 모드' })).toBeVisible({ timeout: 12000 });
  await expect(page.locator('.comment')).toHaveCount(0);
  await page.getByRole('button', { name: '시작', exact: true }).click();
  await expect(page.locator('.connection')).toHaveAttribute('data-state', 'connected');
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

test('account entry, validation, switching and reconnect session boundary', async ({ page }) => {
  let send: (value: string) => void;
  let generation = 0;
  const status = (username: string | null) => JSON.stringify({ type: 'status', source: 'tiktok',
    state: username ? 'connected' : 'idle', message: username ? '연결됨' : '계정 입력 대기',
    session_id: String(generation), comment_history_size: 30, username });
  await page.routeWebSocket('**/ws', (socket) => {
    send = (value) => socket.send(value);
    send(status(null));
  });
  await page.route('**/config', async route => {
    if (route.request().method() === 'GET') {
      const response = await route.fetch();
      await route.fulfill({ json: { ...await response.json(), session_id: String(generation) } });
    } else {
      generation++;
      send(status('first'));
      await route.fulfill({ json: {} });
    }
  });
  await page.route('**/account', async (route) => {
    if (route.request().method() === 'DELETE') {
      generation++;
      send(status(null));
      await route.fulfill({ json: {} });
      return;
    }
    const { username } = route.request().postDataJSON();
    if (username === 'invalid/url') { await route.fulfill({ status: 422, body: '{}' }); return; }
    generation++;
    send(status(username.replace('@', '')));
    await route.fulfill({ json: {} });
    send(JSON.stringify({ type: 'comment', id: String(generation), received_at: new Date().toISOString(),
      user: { nickname: username, unique_id: username }, comment: `새 방송 ${username}` }));
  });
  await page.setViewportSize({ width: 720, height: 1280 });
  await page.goto('/');
  const input = page.getByLabel('TikTok 아이디 또는 방송 주소');
  await expect(input).toBeVisible();
  const field = await input.boundingBox();
  const hint = await page.locator('#account-hint').boundingBox();
  expect(field!.height).toBeGreaterThanOrEqual(44);
  expect(hint!.y - (field!.y + field!.height)).toBeGreaterThanOrEqual(12);
  await page.screenshot({ path: 'test-results/account-entry.png' });
  await input.fill('invalid/url');
  await page.getByRole('button', { name: '시작', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await input.fill('@first');
  await page.getByRole('button', { name: '시작', exact: true }).click();
  await expect(page.locator('.comment')).toHaveCount(1);
  await page.getByRole('button', { name: '모니터 설정' }).click();
  const liveDialog = page.getByRole('dialog', { name: '실제 방송 설정' });
  await expect(liveDialog).toBeVisible();
  await expect(liveDialog.getByRole('radio')).toHaveCount(0);
  await expect(input).toHaveCount(0);
  await expect(liveDialog.getByLabel('데모 댓글 간격 (초)')).toHaveCount(0);
  await liveDialog.getByText('고급 설정', { exact: true }).click();
  await liveDialog.getByLabel('재연결 최소 간격 (초)').fill('20');
  await liveDialog.getByLabel('재연결 최대 간격 (초)').fill('2');
  await liveDialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(liveDialog.getByRole('alert')).toContainText('최소 간격 이상');
  await liveDialog.getByLabel('재연결 최대 간격 (초)').fill('30');
  const applied = page.waitForRequest(r => r.url().endsWith('/config') && r.method() === 'PATCH');
  await liveDialog.getByRole('button', { name: '적용', exact: true }).click();
  expect((await applied).postDataJSON()).toMatchObject({ session_id: String(generation - 1), settings: { tiktok_reconnect_min_seconds: 20 } });
  await expect(liveDialog).toBeHidden();
  await page.getByRole('button', { name: '모니터 종료 · 처음으로' }).click();
  await expect(input).toBeVisible();
  await expect(page.locator('.comment')).toHaveCount(0);
  await input.fill('@second');
  await page.getByRole('button', { name: '시작', exact: true }).click();
  await expect(page.locator('.comment')).toHaveCount(1);
  await expect(page.locator('.body')).toHaveText('새 방송 @second');
  await page.screenshot({ path: 'test-results/account-selected.png' });
  send!(status('second'));
  await expect(page.locator('.comment')).toHaveCount(1);
  generation++;
  send!(status(null));
  await expect(input).toBeVisible();
  await expect(page.locator('.comment')).toHaveCount(0);
});

test('toolbar icons show accessible tooltips and reset every monitor', async ({ page, context, request }) => {
  await startMock(request);
  await page.goto('/');
  await expect(page.locator('.comment')).toHaveCount(30);
  const other = await context.newPage();
  await other.goto('/');
  await expect(other.locator('.comment')).toHaveCount(30);
  const change = page.getByRole('button', { name: '모니터 설정' });
  const reset = page.getByRole('button', { name: '모니터 종료 · 처음으로' });
  await expect(change.locator('svg')).toBeVisible();
  await reset.hover();
  await expect(page.getByRole('tooltip', { name: '모니터 종료 · 처음으로' })).toBeVisible();
  await reset.focus();
  await reset.press('Escape');
  await expect(page.getByRole('tooltip', { name: '모니터 종료 · 처음으로' })).toBeHidden();
  await change.focus();
  await expect(page.getByRole('tooltip', { name: '모니터 설정' })).toBeVisible();
  await page.screenshot({ path: 'test-results/monitor-toolbar.png' });
  const before = (await (await request.get('/health')).json()).source;
  const oldIds = await other.locator('.comment').evaluateAll(nodes => nodes.map(n => n.getAttribute('data-comment-id')));
  // Cancelling settings leaves the current receiver unchanged.
  await change.click();
  await page.getByLabel('목록 보관 수').fill('8');
  await page.getByRole('button', { name: '취소', exact: true }).click();
  const refresh = page.getByRole('button', { name: '댓글 비우기 · 다시 연결' });
  const posted = page.waitForRequest(r => r.url().endsWith('/refresh') && r.method() === 'POST');
  await refresh.click();
  expect((await posted).postDataJSON()).toEqual({ session_id: before.session_id });
  await expect(page.getByRole('group', { name: '실행 모드' })).toBeHidden();
  const after = (await (await request.get('/health')).json()).source;
  expect(after.session_id).not.toBe(before.session_id);
  expect(after.source).toBe(before.source);
  expect(after.username).toBe(before.username);
  for (const monitor of [page, other]) {
    await expect.poll(() => monitor.locator('.comment').evaluateAll(
      (nodes, ids) => nodes.some(n => ids.includes(n.getAttribute('data-comment-id'))), oldIds
    )).toBe(false);
  }
  await page.route('**/account', route => route.fulfill({ status: 500, json: {} }));
  await page.route('**/refresh', route => route.fulfill({ status: 500, json: {} }));
  await refresh.click();
  await expect(page.getByRole('alert')).toContainText('요청 응답을 받지 못했습니다');

  await reset.click();
  await expect(page.getByRole('alert')).toContainText('요청 응답을 받지 못했습니다');
  await expect(page.locator('.comment')).toHaveCount(30);
  await page.unroute('**/account');
  await page.unroute('**/refresh');
  await reset.click();
  for (const monitor of [page, other]) {
    await expect(monitor.getByRole('group', { name: '실행 모드' })).toBeVisible();
    await expect(monitor.getByRole('radio', { name: '데모 체험' })).toBeChecked();
    await expect(monitor.locator('.comment')).toHaveCount(0);
  }
  expect((await (await request.get('/health')).json()).source.state).toBe('idle');
  await other.close();
});

test('settings modal applies validated runtime values to all screens and cancels drafts', async ({ page, context, request }) => {
  await startMock(request);
  await page.setViewportSize({ width: 720, height: 1280 });
  await page.goto('/');
  await expect(page.locator('.comment')).toHaveCount(30);
  const other = await context.newPage();
  await other.goto('/');
  const before = await (await request.get('/config')).json();
  const open = page.getByRole('button', { name: '모니터 설정' });
  const dialog = page.getByRole('dialog', { name: '데모 설정' });
  await open.click();
  await expect(dialog.getByLabel('목록 보관 수')).toHaveValue('30');
  await dialog.getByLabel('목록 보관 수').fill('7');
  await expect(dialog.getByLabel('재연결 최소 간격 (초)')).toHaveCount(0);
  await expect(dialog.getByLabel('재연결 최대 간격 (초)')).toHaveCount(0);
  await expect(dialog.getByRole('radio')).toHaveCount(0);
  await expect(dialog.getByLabel('TikTok 아이디 또는 방송 주소')).toHaveCount(0);
  expect(await (await request.get('/config')).json()).toEqual(before);
  await dialog.getByRole('button', { name: '취소' }).click();
  await expect(dialog).toBeHidden();
  await expect(open).toBeFocused();
  await open.click();
  await expect(dialog.getByLabel('목록 보관 수')).toHaveValue('30');
  await dialog.getByLabel('목록 보관 수').fill('7');
  await dialog.getByText('고급 설정', { exact: true }).click();
  await dialog.getByLabel('수신 대기 큐 크기').fill('20');
  await dialog.getByLabel('데모 댓글 간격 (초)').fill('0.1');
  await dialog.evaluate(element => Promise.all(element.getAnimations({ subtree: true }).map(animation => animation.finished)));
  await page.screenshot({ path: 'test-results/settings-modal.png' });
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(dialog).toBeHidden();
  for (const monitor of [page, other]) await expect(monitor.locator('.comment')).toHaveCount(7);
  const after = await (await request.get('/config')).json();
  expect(after.comment_history_size).toBe(7);
  expect(after.comment_queue_size).toBe(20);
  expect(after.mock_interval_seconds).toBe(0.1);
  expect(after.tiktok_reconnect_min_seconds).toBe(before.tiktok_reconnect_min_seconds);
  expect(after.tiktok_reconnect_max_seconds).toBe(before.tiktok_reconnect_max_seconds);
  expect((await (await request.get('/health')).json()).source).toMatchObject({ source: 'mock', username: null });
  await open.click();
  await expect(dialog.getByLabel('목록 보관 수')).toHaveValue('7');
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await other.close();
});


test('stale settings cannot restart a monitor stopped by another screen', async ({ page, request }) => {
  await startMock(request);
  await page.goto('/');
  await page.getByRole('button', { name: '모니터 설정' }).click();
  const dialog = page.getByRole('dialog', { name: '데모 설정' });
  await expect(dialog.getByLabel('목록 보관 수')).toBeEnabled();
  await change(request, 'DELETE', '/account');
  await dialog.getByLabel('목록 보관 수').fill('9');
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('다른 화면에서 상태가 변경');
  expect((await (await request.get('/health')).json()).source.state).toBe('idle');
  await dialog.getByRole('button', { name: '취소' }).click();
  await expect(page.getByRole('button', { name: '시작', exact: true })).toBeVisible();
});

test('development proxy preserves origin for start, settings and refresh', async ({ page, request }) => {
  await change(request, 'DELETE', '/account');
  const dev = spawn(process.execPath, [resolve('node_modules/vite/bin/vite.js'),
    '--host', '127.0.0.1', '--port', '18766', '--strictPort'], {
    cwd: resolve('.'), env: { ...process.env, BACKEND_URL: 'http://127.0.0.1:18765' }, stdio: 'pipe'
  });
  let logs = '';
  dev.stderr?.on('data', chunk => logs = (logs + chunk.toString()).slice(-2000));
  try {
    await expect.poll(async () => {
      if (dev.exitCode !== null) throw new Error(logs);
      try { return (await request.get('http://127.0.0.1:18766/health')).ok(); } catch { return false; }
    }, { timeout: 15000 }).toBe(true);
    await page.goto('http://127.0.0.1:18766');
    await page.getByRole('button', { name: '시작', exact: true }).click();
    await expect(page.locator('.comment').first()).toBeVisible();
    await page.getByRole('button', { name: '모니터 설정' }).click();
    const dialog = page.getByRole('dialog', { name: '데모 설정' });
    await dialog.getByLabel('목록 보관 수').fill('6');
    await dialog.getByRole('button', { name: '적용', exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(page.locator('.comment')).toHaveCount(6);
    const before = (await (await request.get('/config')).json()).session_id;
    await page.getByRole('button', { name: '댓글 비우기 · 다시 연결' }).click();
    await expect.poll(async () => (await (await request.get('/config')).json()).session_id).not.toBe(before);
  } finally {
    if (dev.exitCode === null) {
      const exited = once(dev, 'exit');
      dev.kill('SIGTERM');
      await exited;
    }
  }
});

test('mock shows profiles, badges, all activities and broadcast lifecycle independently of server connection', async ({ page, request }) => {
  await startMock(request);
  await change(request, 'PATCH', '/config', { settings: { mock_interval_seconds: 0.3, comment_history_size: 30 } });
  await page.setViewportSize({ width: 720, height: 1280 });
  await page.route('**/demo-avatar-1.svg', route => route.fulfill({ status: 404, body: '' }));
  await page.goto('/');
  await expect(page.locator('.live-metrics')).toContainText('시청자');
  await expect(page.locator('.live-metrics')).not.toContainText('—');
  await expect(page.locator('.user-badge[data-kind=fan]').first()).toContainText('Lv.');
  await expect(page.locator('.user-badge[data-kind=subscriber]').first()).toContainText('구독자');
  for (const kind of ['gift', 'follow', 'share', 'subscribe']) {
    await expect(page.locator(`[data-kind=${kind}].activity`).first()).toBeAttached();

  }
  await expect(page.locator('.activity[data-kind=gift] .body').first()).toHaveText('장미 × 5');
  await expect.poll(() => page.locator('.avatar img').evaluateAll(nodes => nodes.some(n =>
    (n as HTMLImageElement).complete && (n as HTMLImageElement).naturalWidth > 0))).toBe(true);
  await expect(page.locator('.avatar img[src="/demo-avatar-1.svg"]')).toHaveCount(0);
  await expect(page.locator('.avatar > span').first()).toBeAttached();
  await expect(page.locator('.broadcast-state')).toHaveText('방송 일시정지');
  await expect(page.locator('.connection')).toHaveText('서버 연결됨');
  await expect(page.locator('.broadcast-state')).toHaveText('방송 중');
  await expect(page.locator('.broadcast-state')).toHaveText('방송 종료');
  await expect(page.locator('.connection')).toHaveText('서버 연결됨');
  await page.screenshot({ path: 'test-results/live-info-and-activities.png' });
  await expect(page.locator('.broadcast-state')).toHaveText('방송 중');
  await page.getByRole('button', { name: '모니터 종료 · 처음으로' }).click();
  await expect(page.locator('.live-summary')).toHaveCount(0);
  await expect(page.locator('.activity')).toHaveCount(0);
});

test('account chip copies the handle and reports clipboard failure', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
      writeText: async (text: string) => Object.defineProperty(window, 'copiedId', { value: text, configurable: true })
    } });
  });
  await page.routeWebSocket('**/ws', socket => socket.send(JSON.stringify({
    type: 'status', source: 'tiktok', state: 'connected', message: '', session_id: 'chip-test',
    username: 'test_account', comment_history_size: 30
  })));
  await page.goto('/');
  const chip = page.getByRole('button', { name: '방송 아이디 복사', exact: true });
  await expect(chip).toHaveText('@test_account');
  await chip.click();
  expect(await page.evaluate(() => Reflect.get(window, 'copiedId'))).toBe('@test_account');
  await expect(page.locator('.copy-feedback')).toHaveText('아이디 복사됨');
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { value: {
    writeText: async () => { throw new Error('Permission denied'); }
  } }));
  await chip.click();
  await expect(page.locator('.copy-feedback')).toContainText('복사하지 못했습니다');
});

test('theme toggle updates the full palette and survives reload without restarting the monitor', async ({ page, request }) => {
  await startMock(request);
  await page.setViewportSize({ width: 720, height: 1280 });
  await page.goto('/');
  const session = (await (await request.get('/config')).json()).session_id;
  await page.getByRole('button', { name: '라이트 테마로 전환', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  await expect(page.locator('html')).toHaveCSS('color', 'rgb(25, 25, 28)');
  await page.getByRole('button', { name: '모니터 설정' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('dialog').getByLabel('목록 보관 수')).toBeEnabled();
  await page.screenshot({ path: 'test-results/light-theme-settings.png', animations: 'disabled' });
  await page.getByRole('button', { name: '취소', exact: true }).click();
  await page.reload();
  await expect(page.getByRole('button', { name: '다크 테마로 전환', exact: true })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  expect((await (await request.get('/config')).json()).session_id).toBe(session);
  await page.screenshot({ path: 'test-results/light-theme-monitor.png' });
  await page.getByRole('button', { name: '다크 테마로 전환', exact: true }).click();
  await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(0, 0, 0)');
  await page.reload();
  await expect(page.getByRole('button', { name: '라이트 테마로 전환', exact: true })).toBeVisible();
});

test('font scale is visible, persists, validates saved values and tolerates blocked storage', async ({ page, request }) => {
  await startMock(request);
  await page.goto('/');
  const output = page.getByRole('group', { name: '댓글 글자 크기', exact: true }).locator('output');
  await expect(output).toContainText('100%');
  const session = (await (await request.get('/config')).json()).session_id;
  await page.getByRole('button', { name: '댓글 글자 크게', exact: true }).click();
  await expect(output).toContainText('105%');
  await page.reload();
  await expect(output).toContainText('105%');
  expect((await (await request.get('/config')).json()).session_id).toBe(session);
  await page.evaluate(() => localStorage.setItem('monitor-font-scale', '103'));
  await page.reload();
  await expect(output).toContainText('100%');
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new Error('Blocked'); }; });
  await page.getByRole('button', { name: '댓글 글자 작게', exact: true }).click();
  await expect(output).toContainText('95%');
});

test('empty view follows server and broadcast states while existing comments remain', async ({ page }) => {
  let send: (data: object) => void;
  await page.routeWebSocket('**/ws', socket => { send = data => socket.send(JSON.stringify(data)); });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '방송 상태를 확인하고 있어요.' })).toBeVisible();
  const status = { type: 'status', source: 'tiktok', state: 'waiting', message: '', session_id: 'state-test',
    username: 'viewer', comment_history_size: 30, live: { state: 'unknown', viewers: null, likes: null } };
  send!(status);
  await expect(page.getByRole('heading', { name: '방송 시작을 기다리고 있어요.' })).toBeVisible();
  send!({ ...status, state: 'connected', live: { ...status.live, state: 'paused' } });
  await expect(page.getByRole('heading', { name: '방송이 잠시 멈췄습니다.' })).toBeVisible();
  send!({ ...status, state: 'connected', live: { ...status.live, state: 'live' } });
  await expect(page.getByRole('heading', { name: '첫 댓글을 기다리고 있어요.' })).toBeVisible();
  send!({ type: 'comment', id: 'keep', received_at: new Date().toISOString(), user: { nickname: 'n', unique_id: 'u' }, comment: '유지할 댓글' });
  await expect(page.locator('.body')).toHaveText('유지할 댓글');
  send!({ ...status, live: { ...status.live, state: 'ended' } });
  await expect(page.locator('.broadcast-state')).toHaveText('방송 종료');
  await expect(page.locator('.body')).toHaveText('유지할 댓글');
});

test('uncertain settings can close and only read status until the server finishes', async ({ page, request }) => {
  await startMock(request);
  let writes = 0;
  let pending = 1;
  await page.route('**/config', route => {
    if (route.request().method() === 'PATCH') { writes++; return route.abort('failed'); }
    return route.continue();
  });
  await page.route('**/health', async route => {
    const response = await route.fetch();
    await route.fulfill({ json: { ...await response.json(), pending_commands: pending } });
  });
  await page.goto('/');
  await page.getByRole('button', { name: '모니터 설정', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('button', { name: '적용', exact: true })).toBeEnabled();
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(dialog).toContainText('서버에서 요청을 처리 중');
  await expect(dialog.getByRole('button', { name: '적용', exact: true })).toBeDisabled();
  await dialog.getByRole('button', { name: '닫기', exact: true }).click();
  const refresh = page.getByRole('button', { name: '댓글 비우기 · 다시 연결' });
  await expect(refresh).toBeDisabled();
  pending = 0;
  await page.getByRole('button', { name: '상태 다시 확인', exact: true }).click();
  await expect(refresh).toBeEnabled();
  expect(writes).toBe(1);
});

test('settings request timeout releases the dialog and accepts an already received session boundary', async ({ page }) => {
  let send: (data: object) => void;
  const status = (session: string) => ({ type: 'status', source: 'mock', state: 'connected', message: '',
    session_id: session, username: null, comment_history_size: 30 });
  await page.routeWebSocket('**/ws', socket => {
    send = data => socket.send(JSON.stringify(data));
    send(status('before-timeout'));
  });
  let writes = 0;
  let healthReads = 0;
  await page.route('**/config', async route => {
    if (route.request().method() === 'PATCH') {
      writes++;
      send(status('after-timeout'));
      return; // Intentionally leave the HTTP response pending past the deadline.
    }
    const response = await route.fetch();
    await route.fulfill({ json: { ...await response.json(), session_id: 'before-timeout' } });
  });
  await page.route('**/health', route => { healthReads++; return route.abort('failed'); });
  await page.goto('/');
  await page.getByRole('button', { name: '모니터 설정', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('button', { name: '적용', exact: true })).toBeEnabled();
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(dialog.getByRole('button', { name: '닫기', exact: true })).toBeEnabled({ timeout: 20000 });
  await expect(dialog).toContainText('서버의 상태 변경을 확인');
  await dialog.getByRole('button', { name: '닫기', exact: true }).click();
  await expect(page.getByRole('button', { name: '댓글 비우기 · 다시 연결' })).toBeEnabled();
  expect(writes).toBe(1);
  expect(healthReads).toBe(0);
});

test('reading mode preserves its anchor, bounds unread items and resets across queued session changes', async ({ page }) => {
  let send: (data: object) => void;
  const status = (session: string) => ({ type: 'status', source: 'mock', state: 'connected', message: '',
    session_id: session, username: null, comment_history_size: 30,
    live: { state: 'live', viewers: 10, likes: 20 } });
  const batch = (from: number, count: number, prefix = 'reading') => {
    for (let i = from; i < from + count; i++) send({ type: 'comment', id: `${prefix}-${i}`,
      received_at: '2026-09-15T00:00:00Z', user: { nickname: `시청자 ${i}`, unique_id: `viewer${i}` },
      comment: `차례대로 읽는 댓글 ${i}` });
  };
  await page.routeWebSocket('**/ws', socket => {
    send = data => socket.send(JSON.stringify(data));
    send(status('reading-session'));
  });
  await page.setViewportSize({ width: 720, height: 1280 });
  await page.goto('/');
  await expect(page.locator('.broadcast-state')).toHaveText('방송 중');
  batch(0, 30);
  const viewport = page.getByRole('region', { name: '실시간 댓글과 활동', exact: true });
  const rows = page.locator('.comment');
  const controls = page.locator('.reading-controls');
  const bottomGap = () => viewport.evaluate(node => Math.abs(node.scrollHeight - node.clientHeight - node.scrollTop));
  const anchor = () => viewport.evaluate(node => {
    const top = node.getBoundingClientRect().top;
    const first = [...node.querySelectorAll<HTMLElement>('[data-comment-id]')]
      .find(item => item.getBoundingClientRect().bottom > top + 1)!;
    return { id: first.dataset.commentId, offset: first.getBoundingClientRect().top - top };
  });
  await expect(rows).toHaveCount(30);
  await expect.poll(bottomGap).toBeLessThanOrEqual(1);
  await viewport.evaluate(node => {
    const item = node.querySelector('[data-comment-id="reading-10"]')!;
    node.scrollTop += item.getBoundingClientRect().top - node.getBoundingClientRect().top + 13;
  });
  await expect(controls).toContainText('이전 댓글을 읽는 중');
  const before = await anchor();
  expect(before.id).toBe('reading-10');
  batch(30, 5);
  await expect(rows.first()).toHaveAttribute('data-comment-id', 'reading-5');
  await expect(rows.last()).toHaveAttribute('data-comment-id', 'reading-34');
  await expect.poll(async () => (await anchor()).id).toBe(before.id);
  await expect.poll(async () => Math.abs((await anchor()).offset - before.offset)).toBeLessThanOrEqual(1);
  await expect(controls).toContainText('보관 중인 새 항목 5개');

  await page.getByRole('button', { name: '댓글 글자 크게', exact: true }).click();
  await expect(page.getByRole('group', { name: '댓글 글자 크기', exact: true })).toContainText('105%');
  await expect.poll(async () => (await anchor()).id).toBe(before.id);
  await expect.poll(async () => Math.abs((await anchor()).offset - before.offset)).toBeLessThanOrEqual(1);
  batch(35, 30);
  await expect(rows.first()).toHaveAttribute('data-comment-id', 'reading-35');
  await expect(rows.last()).toHaveAttribute('data-comment-id', 'reading-64');
  await expect(rows).toHaveCount(30);
  await expect(controls).toContainText('읽던 항목이 보관 범위를 벗어났습니다.');
  await expect(controls).toContainText('보관 중인 새 항목 30개');
  await page.getByRole('button', { name: '최신 댓글로', exact: true }).click();
  await expect(controls).toHaveCount(0);
  await expect(viewport).toBeFocused();
  await expect.poll(bottomGap).toBeLessThanOrEqual(1);

  await viewport.press('PageUp');
  await expect(controls).toContainText('이전 댓글을 읽는 중');
  await viewport.press('Home');
  await expect.poll(() => viewport.evaluate(node => node.scrollTop)).toBe(0);
  await viewport.press('End');
  await expect(controls).toHaveCount(0);
  await expect.poll(bottomGap).toBeLessThanOrEqual(1);
  await viewport.press('ArrowDown');
  await viewport.press('PageDown');
  await viewport.dispatchEvent('wheel', { deltaY: -120, ctrlKey: true });
  await expect(controls).toHaveCount(0);
  await viewport.press('Home');
  await expect(controls).toContainText('이전 댓글을 읽는 중');
  await expect.poll(() => viewport.evaluate(node => node.scrollTop)).toBe(0);

  // Hold browser frames so old-session messages cannot render before the boundary.
  await page.evaluate(() => {
    const originalRequest = window.requestAnimationFrame.bind(window);
    const originalCancel = window.cancelAnimationFrame.bind(window);
    const frames = new Map<number, FrameRequestCallback>();
    let nextId = 1_000_000;
    window.requestAnimationFrame = callback => { frames.set(++nextId, callback); return nextId; };
    window.cancelAnimationFrame = id => { if (!frames.delete(id)) originalCancel(id); };
    Reflect.set(window, 'heldMonitorFrames', () => frames.size);
    Reflect.set(window, 'releaseMonitorFrames', () => {
      window.requestAnimationFrame = originalRequest;
      window.cancelAnimationFrame = originalCancel;
      for (const callback of frames.values()) callback(performance.now());
      frames.clear();
    });
  });
  batch(65, 5);
  await expect.poll(() => page.evaluate(() => Reflect.get(window, 'heldMonitorFrames')())).toBe(1);
  await expect(rows.last()).toHaveAttribute('data-comment-id', 'reading-64');
  send!(status('next-reading-session'));
  await expect(rows).toHaveCount(0);
  await expect(controls).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => Reflect.get(window, 'heldMonitorFrames')())).toBe(0);
  batch(0, 35, 'next');
  await expect.poll(() => page.evaluate(() => Reflect.get(window, 'heldMonitorFrames')())).toBe(1);
  await expect(rows).toHaveCount(0);
  await page.evaluate(() => Reflect.get(window, 'releaseMonitorFrames')());
  await expect(rows).toHaveCount(30);
  await expect.poll(() => rows.evaluateAll(nodes => nodes.map(node => node.getAttribute('data-comment-id'))))
    .toEqual(Array.from({ length: 30 }, (_, i) => `next-${i + 5}`));
  await expect(controls).toHaveCount(0);
  await expect.poll(bottomGap).toBeLessThanOrEqual(1);
});
