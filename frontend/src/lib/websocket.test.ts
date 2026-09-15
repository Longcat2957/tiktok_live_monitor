import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appendComment } from './history';
import { parseMessage, type CommentMessage } from './types';
import { connectMonitor, websocketUrl } from './websocket';

const comment = (id: string): CommentMessage => ({ type: 'comment', id, received_at: '2026-09-12T10:30:00Z', user: { nickname: '민수', unique_id: 'minsu' }, comment: '<script>hello</script> 💚' });

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn(() => this.onclose?.());
  constructor(public url: string) { FakeSocket.instances.push(this); }
}

beforeEach(() => { vi.useFakeTimers(); FakeSocket.instances = []; vi.stubGlobal('WebSocket', FakeSocket); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('message validation', () => {
  it.each(['{', 'null', '[]', '1', '{"type":"gift"}', '{"type":"comment","id":"x"}', '{"type":"status","source":"wrong","state":"connected","message":"ok"}'])('ignores malformed payload %s', (raw) => expect(parseMessage(raw)).toBeNull());
  it('accepts a valid comment without changing its content', () => expect(parseMessage(JSON.stringify(comment('a')))).toEqual(comment('a')));
  it('rejects invalid date and empty body', () => {
    expect(parseMessage(JSON.stringify({ ...comment('a'), received_at: 'invalid' }))).toBeNull();
    expect(parseMessage(JSON.stringify({ ...comment('a'), comment: ' ' }))).toBeNull();
  });
});

it('bounds history and preserves order, including after repeated IDs', () => {
  let history: CommentMessage[] = [];
  for (let i = 0; i < 10000; i++) history = appendComment(history, comment(String(i)), 30);
  expect(history).toHaveLength(30);
  expect(history[0].id).toBe('9970');
  expect(appendComment(history, comment('9999'), 30)).toBe(history);
});

it('uses same-origin ws and wss', () => {
  expect(websocketUrl({ protocol: 'https:', host: 'monitor.test' })).toBe('wss://monitor.test/ws');
  expect(websocketUrl({ protocol: 'http:', host: 'monitor.test:8000' })).toBe('ws://monitor.test:8000/ws');
});

it('reconnects with bounded backoff, resets on open and retains history', () => {
  let history: CommentMessage[] = [];
  const state = vi.fn();
  const stop = connectMonitor('ws://monitor/ws', (message) => {
    if (message.type === 'comment') history = appendComment(history, message, 30);
  }, state);
  const first = FakeSocket.instances[0];
  first.onopen?.();
  first.onmessage?.({ data: '{broken' });
  first.onmessage?.({ data: JSON.stringify(comment('a')) });
  first.onclose?.();
  expect(state).toHaveBeenLastCalledWith('disconnected');
  vi.advanceTimersByTime(1000);
  expect(FakeSocket.instances).toHaveLength(2);
  FakeSocket.instances[1].onclose?.();
  vi.advanceTimersByTime(1999);
  expect(FakeSocket.instances).toHaveLength(2);
  vi.advanceTimersByTime(1);
  for (let i = 0; i < 10; i++) {
    FakeSocket.instances.at(-1)?.onclose?.();
    vi.advanceTimersByTime(30000);
  }
  const last = FakeSocket.instances.at(-1)!;
  last.onopen?.();
  last.onclose?.();
  const count = FakeSocket.instances.length;
  vi.advanceTimersByTime(1000);
  expect(FakeSocket.instances).toHaveLength(count + 1);
  expect(history).toEqual([comment('a')]);
  stop();
  vi.advanceTimersByTime(60000);
  expect(FakeSocket.instances).toHaveLength(count + 1);
});

it('clears a pending retry on unmount', () => {
  const stop = connectMonitor('ws://monitor/ws', vi.fn(), vi.fn());
  FakeSocket.instances[0].onclose?.();
  stop();
  vi.advanceTimersByTime(60000);
  expect(FakeSocket.instances).toHaveLength(1);
});
