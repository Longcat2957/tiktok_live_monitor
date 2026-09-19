import { afterEach, expect, it, vi } from 'vitest';
import { requestJson } from './api';

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

it.each(['headers', 'body'])(
    'times out while waiting for %s and cleans up its timer',
    async (phase) => {
        vi.useFakeTimers();
        vi.stubGlobal(
            'fetch',
            vi.fn((_path, init: RequestInit) => {
                const stalled = () =>
                    new Promise((_resolve, reject) =>
                        init.signal?.addEventListener(
                            'abort',
                            () => reject(new DOMException('Aborted', 'AbortError')),
                            { once: true },
                        ),
                    );
                return phase === 'headers'
                    ? stalled()
                    : Promise.resolve({ ok: true, status: 200, json: stalled });
            }),
        );
        const rejected = expect(requestJson('/config', {}, 50)).rejects.toMatchObject({
            name: 'AbortError',
        });
        await vi.advanceTimersByTimeAsync(50);
        await rejected;
        expect(vi.getTimerCount()).toBe(0);
        expect(fetch).toHaveBeenCalledTimes(1);
    },
);

it('cleans up after success and reports HTTP status for the caller', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
        'fetch',
        vi.fn(async () => new Response('{"detail":"conflict"}', { status: 409 })),
    );
    expect(await requestJson('/account')).toEqual({
        ok: false,
        status: 409,
        data: { detail: 'conflict' },
    });
    expect(vi.getTimerCount()).toBe(0);
});
