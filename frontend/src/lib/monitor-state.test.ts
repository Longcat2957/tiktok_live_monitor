import { describe, expect, it } from 'vitest';
import { monitorView, type MonitorView } from './monitor-state';
import type { BackendState, LiveInfo, SourceState, StatusMessage } from './types';

function status(state: SourceState, live?: LiveInfo['state']): StatusMessage {
  return {
    type: 'status', source: 'tiktok', state, message: '', session_id: 'session',
    username: 'host', comment_history_size: 30,
    ...(live ? { live: { state: live, viewers: null, likes: null } } : {})
  };
}

describe('monitor view', () => {
  it.each<{
    name: string; backend: BackendState; source: StatusMessage | null;
    kind: MonitorView['kind']; label: string; tone: MonitorView['tone'];
  }>([
    { name: 'initial server connection', backend: 'connecting', source: null,
      kind: 'server-connecting', label: '방송 상태 확인 중', tone: 'waiting' },
    { name: 'server reconnect hides stale live state', backend: 'connecting', source: status('connected', 'live'),
      kind: 'server-connecting', label: '방송 상태 확인 중', tone: 'waiting' },
    { name: 'server disconnect hides stale live state', backend: 'disconnected', source: status('connected', 'live'),
      kind: 'server-disconnected', label: '방송 상태 확인 불가', tone: 'error' },
    { name: 'connected socket awaiting status', backend: 'connected', source: null,
      kind: 'checking', label: '방송 상태 확인 중', tone: 'waiting' },
    { name: 'idle account selection', backend: 'connected', source: status('idle'),
      kind: 'idle', label: '방송 선택 대기', tone: 'neutral' },
    { name: 'source connecting', backend: 'connected', source: status('connecting'),
      kind: 'connecting', label: '방송 연결 중', tone: 'waiting' },
    { name: 'offline broadcast', backend: 'connected', source: status('waiting'),
      kind: 'waiting', label: '방송 시작 대기', tone: 'waiting' },
    { name: 'source disconnected with stale paused state', backend: 'connected', source: status('disconnected', 'paused'),
      kind: 'disconnected', label: '방송 재연결 대기', tone: 'waiting' },
    { name: 'source error overrides last broadcast state', backend: 'connected', source: status('error', 'ended'),
      kind: 'error', label: '댓글 수신 오류', tone: 'error' },
    { name: 'paused live', backend: 'connected', source: status('connected', 'paused'),
      kind: 'paused', label: '방송 일시정지', tone: 'waiting' },
    { name: 'ended live', backend: 'connected', source: status('connected', 'ended'),
      kind: 'ended', label: '방송 종료', tone: 'neutral' },
    { name: 'ended live waiting to reconnect', backend: 'connected', source: status('waiting', 'ended'),
      kind: 'ended', label: '방송 종료', tone: 'neutral' },
    { name: 'ended live reconnecting', backend: 'connected', source: status('connecting', 'ended'),
      kind: 'ended', label: '방송 종료', tone: 'neutral' },
    { name: 'resumed live', backend: 'connected', source: status('connected', 'live'),
      kind: 'listening', label: '방송 중', tone: 'live' },
    { name: 'connected with unknown broadcast state', backend: 'connected', source: status('connected', 'unknown'),
      kind: 'listening', label: '방송 상태 확인 중', tone: 'neutral' },
    { name: 'connected without optional live snapshot', backend: 'connected', source: status('connected'),
      kind: 'listening', label: '방송 상태 확인 중', tone: 'neutral' }
  ])('$name', ({ backend, source, kind, label, tone }) => {
    const view = monitorView(backend, source);
    expect(view).toMatchObject({ kind, label, tone });
    expect(view.title).not.toBe('');
    expect(view.description).not.toBe('');
    expect(view.title === '첫 댓글을 기다리고 있어요.').toBe(kind === 'listening');
  });

  it('preserves actionable source errors without changing the source snapshot', () => {
    const source = { ...status('error'), message: '계정을 찾을 수 없습니다 · 아이디 확인 필요' };
    expect(monitorView('connected', source).description).toBe(source.message);
    expect(monitorView('connected', status('error')).description).toBe('서버와 방송 연결 상태를 확인해주세요.');
    expect(source).toEqual({ ...status('error'), message: '계정을 찾을 수 없습니다 · 아이디 확인 필요' });
  });
});
