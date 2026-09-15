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

it('validates enriched comments, safe avatars, badges and activities', () => {
  const enriched = { ...comment('x'), user: { ...comment('x').user,
    avatar_url: '/demo-avatar-0.svg', badges: [{ kind: 'fan' as const, level: 12 }] } };
  expect(parseMessage(JSON.stringify(enriched))).toEqual(enriched);
  const activity = { type: 'activity', id: 'gift', received_at: enriched.received_at,
    user: enriched.user, kind: 'gift', gift_name: '<b>장미</b>', count: 5 };
  expect(parseMessage(JSON.stringify(activity))).toEqual(activity);
  expect(parseMessage(JSON.stringify({ ...activity, count: 0 }))).toBeNull();
  expect(appendComment<import('./types').FeedMessage>([enriched], activity as import('./types').ActivityMessage, 1)).toEqual([activity]);
});

it('keeps comment text when optional profile data is invalid and never uses unsafe avatars', () => {
  const original = comment('optional');
  for (const avatar_url of ['javascript:alert(1)', '//example.com/a', 'https://user:secret@example.com/a',
    'http://example.com/a', '/unexpected.svg', 123]) {
    const raw = JSON.stringify({ ...original, user: { ...original.user, avatar_url, badges: 'invalid' } });
    expect(parseMessage(raw)).toEqual(original);
  }
  expect(parseMessage(JSON.stringify({ ...original, user: { ...original.user,
    avatar_url: 'https://example.com/avatar.jpg', badges: null } }))).toEqual({ ...original,
    user: { ...original.user, avatar_url: 'https://example.com/avatar.jpg' } });
  for (const user of [null, {}, { nickname: 1, unique_id: 'id' }, { nickname: 'name' },
    { nickname: 'a'.repeat(257), unique_id: 'id' }]) {
    expect(parseMessage(JSON.stringify({ ...original, user }))).toBeNull();
  }
});

it('retains only valid unique badges in receive order for comments and activities', () => {
  const user = { ...comment('badges').user, badges: [
    null, { kind: 'unknown', level: 1 }, { kind: 'fan', level: -1 },
    { kind: 'fan', level: 10001 }, { kind: 'fan', level: 1.5 },
    { kind: 'fan', level: 12 }, { kind: 'fan', level: 99 },
    { kind: 'subscriber', level: null }, { kind: 'subscriber', level: 3 }
  ] };
  const expected = { ...comment('badges').user,
    badges: [{ kind: 'fan', level: 12 }, { kind: 'subscriber', level: null }] };
  const activity = { type: 'activity', id: 'activity', received_at: comment('badges').received_at,
    user, kind: 'follow', gift_name: '', count: 1 };
  for (const message of [{ ...comment('badges'), user }, activity]) {
    expect(parseMessage(JSON.stringify(message))).toEqual({ ...message, user: expected });
  }
  expect(user.badges).toHaveLength(9);
  expect(parseMessage(JSON.stringify({ ...comment('none'), user: { ...user,
    badges: [{ kind: 'fan', level: -1 }] } }))).toEqual({ ...comment('none'),
    user: { ...comment('none').user, badges: [] } });
});

it('validates live snapshots and preserves unknown counts', () => {
  const status = { type: 'status', source: 'mock', state: 'connected', message: '',
    session_id: 's', username: null, comment_history_size: 30,
    live: { state: 'paused', viewers: null, likes: 1000 } };
  expect(parseMessage(JSON.stringify(status))).toEqual(status);
  expect(parseMessage(JSON.stringify({ ...status, live: { ...status.live, viewers: -1 } }))).toBeNull();
});
