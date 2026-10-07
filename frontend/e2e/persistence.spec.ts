import { spawn, type ChildProcess } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const baseURL = 'http://127.0.0.1:18769';
test.use({ baseURL });

interface DbRow {
    event_id: string;
    session_id: string;
    username: string;
}
interface FaultState {
    writer_waiting: boolean;
    rows: DbRow[];
    flow: { received_comments: number; upstream_messages: number };
    snapshots: {
        session_id: string;
        details: { received_comments: number; upstream_messages: number };
    }[];
    health: {
        source: { state: string; session_id: string };
        dropped_comments: number;
        slow_disconnects: number;
        websocket_connections: number;
        storage: {
            ready: boolean;
            error: string | null;
            queued: number;
            dropped: number;
            saved_comments: number;
        };
    };
}

let directory: string;
let server: ChildProcess | undefined;
let logs = '';

async function startServer() {
    logs = '';
    server = spawn(resolve('../backend/.venv/bin/python'), ['tests/browser_fault_server.py'], {
        cwd: resolve('../backend'),
        env: { ...process.env, ARCHIVE_PATH: join(directory, 'monitor.sqlite3') },
        stdio: 'pipe',
    });
    server.stderr?.on('data', (chunk) => {
        logs = (logs + chunk.toString()).slice(-6000);
    });
    server.on('error', (error) => {
        logs = error.message;
    });
    await expect
        .poll(
            async () => {
                if (server?.exitCode !== null) throw new Error(logs);
                try {
                    return (await fetch(`${baseURL}/health`)).ok;
                } catch {
                    return false;
                }
            },
            { timeout: 10000 },
        )
        .toBe(true);
}

async function stopServer() {
    if (server && server.exitCode === null) {
        await fetch(`${baseURL}/__test/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'release' }),
            signal: AbortSignal.timeout(1000),
        }).catch(() => {});
        const exited = once(server, 'exit');
        server.kill('SIGTERM');
        const processToStop = server;
        const timeout = setTimeout(() => processToStop.kill('SIGKILL'), 10000);
        try {
            await exited;
        } finally {
            clearTimeout(timeout);
        }
    }
}

test.beforeEach(async () => {
    directory = await mkdtemp(join(tmpdir(), 'monitor-browser-fault-'));
    await startServer();
});
test.afterEach(async () => {
    try {
        await stopServer();
    } finally {
        await rm(directory, { recursive: true, force: true });
    }
});

async function control(request: APIRequestContext, action: string, prefix = 'test', count = 1) {
    const response = await request.post('/__test/control', { data: { action, prefix, count } });
    expect(response.ok()).toBe(true);
}
async function state(request: APIRequestContext): Promise<FaultState> {
    const response = await request.get('/__test/state');
    expect(response.ok()).toBe(true);
    return response.json();
}
async function start(request: APIRequestContext, username: string): Promise<string> {
    const before = await state(request);
    const response = await request.post('/account', {
        data: { session_id: before.health.source.session_id, source: 'tiktok', username },
    });
    expect(response.ok()).toBe(true);
    const { session_id } = await response.json();
    await expect.poll(async () => (await state(request)).health.source.state).toBe('connected');
    return session_id;
}
const ids = (prefix: string, count: number, start = 0) =>
    Array.from({ length: count }, (_, index) => `${prefix}-${start + index}`);
async function expectLatest(page: Page, prefix: string, total: number) {
    await expect
        .poll(() =>
            page
                .locator('.comment')
                .evaluateAll((rows) => rows.map((row) => row.dataset.commentId)),
        )
        .toEqual(ids(prefix, Math.min(30, total), Math.max(0, total - 30)));
}

test('real feed and HTTP remain responsive through a blocked SQLite writer and archive overflow', async ({
    page,
    request,
}) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    await page.goto('/');
    await expect(page.locator('.connection')).toHaveAttribute('data-state', 'connected');
    const session = await start(request, 'stress.account');
    await control(request, 'block');
    await control(request, 'burst', 'warmup', 100);
    await expect.poll(async () => (await state(request)).writer_waiting).toBe(true);
    await expectLatest(page, 'warmup', 100);
    await control(request, 'burst', 'overflow', 2500);
    await expectLatest(page, 'overflow', 2500);
    const started = performance.now();
    expect((await request.get('/health')).status()).toBe(200);
    expect(performance.now() - started).toBeLessThan(1500);
    const blocked = await state(request);
    expect(blocked.writer_waiting).toBe(true);
    expect(blocked.health.storage.queued).toBeLessThanOrEqual(2100);
    expect(blocked.health.storage.dropped).toBeGreaterThan(0);
    expect(blocked.health.dropped_comments).toBe(0);
    expect(blocked.health.slow_disconnects).toBe(0);
    expect(blocked.health.websocket_connections).toBe(1);
    expect(blocked.flow.received_comments).toBe(2600);
    await control(request, 'release');
    await expect
        .poll(async () => (await state(request)).health.storage.queued, { timeout: 10000 })
        .toBe(0);
    const saved = await state(request);
    expect(
        saved.rows.filter((row) => row.event_id.startsWith('warmup-')).map((row) => row.event_id),
    ).toEqual(ids('warmup', 100));
    const overflow = saved.rows.filter((row) => row.event_id.startsWith('overflow-'));
    expect(overflow.length).toBeGreaterThan(0);
    expect(overflow.length).toBeLessThan(2500);
    expect(overflow.map((row) => row.event_id)).toEqual(ids('overflow', overflow.length));
    expect(
        saved.rows.every((row) => row.session_id === session && row.username === 'stress.account'),
    ).toBe(true);
    expect(errors).toEqual([]);
});

test('queued archive keeps old session attribution while a connected quiet source resumes on screen', async ({
    page,
    request,
}) => {
    await page.goto('/');
    await expect(page.locator('.connection')).toHaveAttribute('data-state', 'connected');
    const before = await start(request, 'before.account');
    await control(request, 'block');
    await control(request, 'burst', 'before', 100);
    await expect.poll(async () => (await state(request)).writer_waiting).toBe(true);
    await expectLatest(page, 'before', 100);
    expect((await request.delete('/account', { data: { session_id: before } })).ok()).toBe(true);
    const after = await start(request, 'after.account');
    expect(after).not.toBe(before);
    await control(request, 'burst', 'after', 60);
    await expectLatest(page, 'after', 60);
    await control(request, 'upstream', 'test', 5);
    await control(request, 'snapshot');
    await page.waitForTimeout(1200);
    await control(request, 'upstream', 'test', 3);
    await control(request, 'snapshot');
    const quiet = await state(request);
    expect(quiet.health.source.state).toBe('connected');
    expect(quiet.health.source.session_id).toBe(after);
    expect(quiet.flow).toMatchObject({ received_comments: 60, upstream_messages: 8 });
    await expectLatest(page, 'after', 60);
    await expect(page.locator('.connection')).toHaveAttribute('data-state', 'connected');
    await control(request, 'release');
    await expect
        .poll(async () => (await state(request)).health.storage.queued, { timeout: 10000 })
        .toBe(0);
    const saved = await state(request);
    expect(saved.rows.map((row) => row.event_id)).toEqual([
        ...ids('before', 100),
        ...ids('after', 60),
    ]);
    expect(
        saved.rows
            .slice(0, 100)
            .every((row) => row.session_id === before && row.username === 'before.account'),
    ).toBe(true);
    expect(
        saved.rows
            .slice(100)
            .every((row) => row.session_id === after && row.username === 'after.account'),
    ).toBe(true);
    expect(
        saved.snapshots.filter((snapshot) => snapshot.session_id === after).at(-1)?.details,
    ).toMatchObject({ received_comments: 60, upstream_messages: 8 });
    await control(request, 'burst', 'resumed', 40);
    await expectLatest(page, 'resumed', 40);
    await expect.poll(async () => (await state(request)).health.storage.saved_comments).toBe(200);
});

test('SQLite failure reports health 503 while the real browser updates, then restart preserves committed rows', async ({
    page,
    request,
}) => {
    await page.goto('/');
    await expect(page.locator('.connection')).toHaveAttribute('data-state', 'connected');
    await start(request, 'failure.account');
    await control(request, 'burst', 'committed', 30);
    await expectLatest(page, 'committed', 30);
    await expect.poll(async () => (await state(request)).health.storage.saved_comments).toBe(30);
    await control(request, 'fail');
    await control(request, 'burst', 'failed', 40);
    await expectLatest(page, 'failed', 40);
    await expect.poll(async () => (await request.get('/health')).status()).toBe(503);
    const failed = await state(request);
    expect(failed.health.storage.error).toBe('write:OperationalError');
    expect(failed.health.source.state).toBe('connected');
    expect(failed.rows.map((row) => row.event_id)).toEqual(ids('committed', 30));
    await control(request, 'burst', 'continued', 35);
    await expectLatest(page, 'continued', 35);
    expect((await state(request)).health.storage.dropped).toBeGreaterThan(0);
    await expect(page.locator('.connection')).toHaveAttribute('data-state', 'connected');
    expect(logs).not.toContain('PRIVATE simulated disk failure');
    await stopServer();
    await startServer();
    await expect(page.getByRole('group', { name: '방송 또는 데모' })).toBeVisible({
        timeout: 12000,
    });
    await expect(page.locator('.comment')).toHaveCount(0);
    const reopened = await state(request);
    expect(reopened.health.storage.ready).toBe(true);
    expect(reopened.rows.map((row) => row.event_id)).toEqual(ids('committed', 30));
    await start(request, 'recovered.account');
    await control(request, 'burst', 'recovered', 40);
    await expectLatest(page, 'recovered', 40);
    await expect.poll(async () => (await state(request)).rows.length).toBe(70);
    expect((await state(request)).rows.map((row) => row.event_id)).toEqual([
        ...ids('committed', 30),
        ...ids('recovered', 40),
    ]);
});
