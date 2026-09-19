import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { writeFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { platform, arch, cpus } from 'node:os';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from '@playwright/test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const listener = createServer().listen(0, '127.0.0.1');
await once(listener, 'listening');
const address = listener.address();
if (!address || typeof address === 'string') throw new Error('Benchmark TCP port is unavailable');
const port = address.port;
await new Promise((r) => listener.close(r));
const server = spawn(
    resolve(root, 'backend/.venv/bin/python'),
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port)],
    { cwd: resolve(root, 'backend'), stdio: 'ignore' },
);
let browser;
/** @type {{ history: number, round: number, count: number, elapsedMs: number, frameP95Ms: number, longestTaskMs: number, longTasks: number }[]} */
const rounds = [];
const report = {
    platform: `${platform()} ${arch()}`,
    cpu: cpus()[0]?.model,
    cpuSlowdown: 4,
    viewport: '1080x1920',
    browser: '',
    rounds,
};
try {
    let ready = false;
    for (let i = 0; i < 50; i++) {
        try {
            if ((await fetch(`http://127.0.0.1:${port}/health`)).ok) {
                ready = true;
                break;
            }
        } catch {
            /* Server may still be starting. */
        }
        await delay(100);
    }
    if (!ready) throw new Error('Benchmark server did not start');
    browser = await chromium.launch({
        headless: true,
        ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
            ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
            : {}),
    });
    report.browser = browser.version();
    for (const history of [30, 1000]) {
        for (let round = 1; round <= 3; round++) {
            const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
            const cdp = await page.context().newCDPSession(page);
            await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
            /** @type {((value: unknown) => void) | undefined} */
            let send;
            await page.routeWebSocket('**/ws', (socket) => {
                send = (value) => socket.send(JSON.stringify(value));
                send({
                    type: 'status',
                    source: 'mock',
                    state: 'connected',
                    message: '',
                    session_id: 'benchmark',
                    username: null,
                    comment_history_size: history,
                });
            });
            await page.goto(`http://127.0.0.1:${port}`);
            await page.getByRole('button', { name: '모니터 설정', exact: true }).waitFor();
            if (!send) throw new Error('Benchmark WebSocket did not connect');
            const measurement = await page.evaluateHandle(() => {
                /** @type {number[]} */
                const frames = [];
                const result = { frames, longTasks: 0, longestTask: 0, running: true };
                let previous = performance.now();
                /** @param {number} now */
                function frame(now) {
                    result.frames.push(now - previous);
                    previous = now;
                    if (result.running) requestAnimationFrame(frame);
                }
                requestAnimationFrame(frame);
                new PerformanceObserver((list) => {
                    for (const entry of list.getEntries()) {
                        result.longTasks++;
                        result.longestTask = Math.max(result.longestTask, entry.duration);
                    }
                }).observe({ type: 'longtask', buffered: false });
                return result;
            });
            const count = 1000;
            const started = performance.now();
            for (let id = 0; id < count; id++) {
                send({
                    type: 'comment',
                    id: String(id),
                    received_at: new Date().toISOString(),
                    user: {
                        nickname: `시청자 ${id % 20}`,
                        unique_id: 'benchmark',
                        badges: [{ kind: 'fan', level: 12 }],
                    },
                    comment: '댓글 수신 순서와 화면 갱신을 확인합니다. Hello LIVE! 💚',
                });
                // 500 events/s target; Node/CDP overhead is included in actual delivery time.
                await delay(2);
            }
            await page.locator(`[data-comment-id="${count - 1}"]`).waitFor({ state: 'attached' });
            const elapsedMs = performance.now() - started;
            const { ids, ...stats } = await measurement.evaluate((data) => {
                data.running = false;
                const frames = data.frames.slice(1).sort((a, b) => a - b);
                return {
                    frameP95Ms: frames[Math.floor(frames.length * 0.95)],
                    longestTaskMs: data.longestTask,
                    longTasks: data.longTasks,
                    ids: Array.from(document.querySelectorAll('[data-comment-id]'), (el) =>
                        el.getAttribute('data-comment-id'),
                    ),
                };
            });
            const expected = Array.from({ length: history }, (_, i) => String(count - history + i));
            if (JSON.stringify(ids) !== JSON.stringify(expected))
                throw new Error('Receive order/history bound mismatch');
            report.rounds.push({ history, round, count, elapsedMs, ...stats });
            await page.close();
        }
    }
    const output = JSON.stringify(report, null, 2) + '\n';
    if (process.argv[2]) await writeFile(resolve(process.argv[2]), output);
    process.stdout.write(output);
} finally {
    await browser?.close();
    if (server.exitCode === null) {
        const done = once(server, 'exit');
        server.kill('SIGTERM');
        await done;
    }
}
