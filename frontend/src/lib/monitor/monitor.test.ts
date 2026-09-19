import { afterEach, expect, it, vi } from 'vitest';
import type { CommentMessage, StatusMessage } from '../types';
import { MonitorSession } from './session.svelte.js';
import { MonitorCommands } from './commands.svelte.js';

const status = (session_id = 'first'): StatusMessage => ({
    type: 'status',
    source: 'mock',
    state: 'connected',
    message: '',
    session_id,
    username: null,
    comment_history_size: 2,
});
const comment = (id: string): CommentMessage => ({
    type: 'comment',
    id,
    received_at: '2026-09-12T10:30:00Z',
    user: { nickname: 'name', unique_id: 'user' },
    comment: id,
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

it('batches ordered bounded history per instance and clears old frames at session changes and disconnect', () => {
    vi.useFakeTimers();
    class Socket {
        static instances: Socket[] = [];
        onmessage: ((event: { data: string }) => void) | null = null;
        onopen: (() => void) | null = null;
        onclose: (() => void) | null = null;
        close = vi.fn();
        constructor() {
            Socket.instances.push(this);
        }
        send(value: unknown) {
            this.onmessage?.({ data: JSON.stringify(value) });
        }
    }
    const frames = new Map<number, FrameRequestCallback>();
    let nextFrame = 0;
    vi.stubGlobal('WebSocket', Socket);
    vi.stubGlobal('window', { location: { protocol: 'https:', host: 'monitor.test' } });
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
        frames.set(++nextFrame, callback);
        return nextFrame;
    });
    vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
    const flush = () => {
        const queued = [...frames.values()];
        frames.clear();
        queued.forEach((callback) => callback(0));
    };
    const first = new MonitorSession();
    const second = new MonitorSession();
    const onStatus = vi.fn((value: StatusMessage) => expect(first.source).toEqual(value));
    const stopFirst = first.connect(onStatus);
    const stopSecond = second.connect(() => {});
    const socket = Socket.instances[0];
    socket.send(status());
    for (let i = 0; i < 100; i++) socket.send(comment(String(i)));
    expect(frames.size).toBe(1);
    expect(first.comments).toEqual([]);
    flush();
    expect(first.comments.map((item) => item.id)).toEqual(['98', '99']);
    expect(second.comments).toEqual([]);

    socket.onclose?.();
    vi.advanceTimersByTime(1000);
    const reconnected = Socket.instances[2];
    reconnected.send(status());
    expect(first.comments.map((item) => item.id)).toEqual(['98', '99']);
    reconnected.send(comment('old pending'));
    reconnected.send(status('second'));
    expect(frames.size).toBe(0);
    expect(first.comments).toEqual([]);
    reconnected.send(comment('new pending'));
    stopFirst();
    expect(frames.size).toBe(0);
    expect(reconnected.close).toHaveBeenCalledOnce();
    stopSecond();
    expect(vi.getTimerCount()).toBe(0);
});

it('blocks uncertain writes and polls without changing the WebSocket-owned session', async () => {
    vi.useFakeTimers();
    const source = status();
    let reads = 0;
    const fetcher = vi.fn(async (path: string) => {
        if (path !== '/health') throw new TypeError('Network unavailable');
        reads++;
        return Response.json({
            source: reads === 1 ? source : status('http snapshot'),
            pending_commands: reads === 1 ? 1 : 0,
        });
    });
    vi.stubGlobal('fetch', fetcher);
    const commands = new MonitorCommands(() => source);
    const other = new MonitorCommands(() => status('other'));
    expect(await commands.refresh()).toContain('요청 응답을 받지 못했습니다.');
    expect(commands.blocked).toBe(true);
    expect(other.blocked).toBe(false);
    expect(await commands.updateSettings({}, 'first')).toContain('이전 요청');
    expect(fetcher).toHaveBeenCalledTimes(2);
    commands.acceptStatus(source);
    await vi.advanceTimersByTimeAsync(3000);
    expect(reads).toBe(2);
    expect(commands.blocked).toBe(false);
    expect(commands.recoveryMessage).toContain('현재 화면을 확인해주세요.');
    expect(source.session_id).toBe('first');
    expect(vi.getTimerCount()).toBe(0);
    commands.dispose();
    other.dispose();
});

it('accepts a new WebSocket session while a health read is pending and cancels recovery on disposal', async () => {
    vi.useFakeTimers();
    let source = status();
    let finishRead: (response: Response) => void = () => {};
    vi.stubGlobal(
        'fetch',
        vi.fn((path: string) =>
            path === '/health'
                ? new Promise<Response>((resolve) => {
                      finishRead = resolve;
                  })
                : Promise.reject(new TypeError('Network unavailable')),
        ),
    );
    const commands = new MonitorCommands(() => source);
    const change = commands.refresh();
    await vi.waitFor(() => expect(commands.checking).toBe(true));
    source = status('second');
    commands.acceptStatus(source);
    finishRead(Response.json({ source: status(), pending_commands: 1 }));
    await change;
    expect(commands.pendingSession).toBeNull();
    expect(commands.actionError).toBe('');
    expect(commands.recoveryMessage).toContain('현재 화면에 반영했습니다.');
    expect(source.session_id).toBe('second');
    expect(vi.getTimerCount()).toBe(0);

    vi.stubGlobal(
        'fetch',
        vi.fn(async () => {
            throw new TypeError('Network unavailable');
        }),
    );
    await commands.refresh();
    expect(vi.getTimerCount()).toBe(1);
    commands.dispose();
    await vi.advanceTimersByTimeAsync(30000);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
});

it('clears a previous action error when another browser moves to a new session', async () => {
    let source = status();
    vi.stubGlobal(
        'fetch',
        vi.fn(async () => Response.json({ detail: 'conflict' }, { status: 409 })),
    );
    const commands = new MonitorCommands(() => source);
    commands.acceptStatus(source);
    await commands.refresh();
    expect(commands.actionError).toContain('새로고침하지 못했습니다.');
    commands.acceptStatus(source);
    expect(commands.actionError).not.toBe('');
    source = status('second');
    commands.acceptStatus(source);
    expect(commands.actionError).toBe('');
    commands.dispose();
});

it('aborts an in-flight mutation without leaving requests or recovery timers on disposal', async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | null | undefined;
    vi.stubGlobal(
        'fetch',
        vi.fn((_path: string, init: RequestInit) => {
            signal = init.signal;
            return new Promise<Response>((_resolve, reject) =>
                signal?.addEventListener('abort', () =>
                    reject(new DOMException('Aborted', 'AbortError')),
                ),
            );
        }),
    );
    const commands = new MonitorCommands(() => status());
    const change = commands.start('mock', '');
    expect(commands.saving).toBe(true);
    commands.dispose();
    expect(await change).toContain('화면이 닫혀');
    expect(signal?.aborted).toBe(true);
    expect(commands.saving).toBe(false);
    expect(commands.pendingSession).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
});
