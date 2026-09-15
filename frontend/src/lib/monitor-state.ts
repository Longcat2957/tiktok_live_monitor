import type { BackendState, StatusMessage } from './types';

const views = {
  'server-connecting': {
    title: '모니터에 연결하고 있어요.', description: '서버에 연결되면 방송 상태를 확인합니다.',
    label: '방송 상태 확인 중', tone: 'waiting'
  },
  'server-disconnected': {
    title: '서버에 연결할 수 없습니다.', description: '자동으로 다시 연결하고 있어요. 연결이 계속 안 되면 서버와 네트워크를 확인해주세요.',
    label: '방송 상태 확인 불가', tone: 'error'
  },
  checking: {
    title: '방송 상태를 확인하고 있어요.', description: '서버에서 현재 모니터 상태를 불러오고 있습니다.',
    label: '방송 상태 확인 중', tone: 'waiting'
  },
  idle: {
    title: '방송을 선택해주세요.', description: '방송 아이디를 입력하거나 데모를 선택해 시작하세요.',
    label: '방송 선택 대기', tone: 'neutral'
  },
  connecting: {
    title: '방송에 연결하고 있어요.', description: '연결되면 댓글과 활동이 여기에 표시됩니다.',
    label: '방송 연결 중', tone: 'waiting'
  },
  waiting: {
    title: '방송 시작을 기다리고 있어요.', description: '방송이 시작되면 자동으로 연결합니다.',
    label: '방송 시작 대기', tone: 'waiting'
  },
  disconnected: {
    title: '방송 연결이 끊겼습니다.', description: '자동으로 다시 연결하고 있어요.',
    label: '방송 재연결 대기', tone: 'waiting'
  },
  error: {
    title: '댓글 수신에 문제가 생겼습니다.', description: '서버와 방송 연결 상태를 확인해주세요.',
    label: '댓글 수신 오류', tone: 'error'
  },
  paused: {
    title: '방송이 잠시 멈췄습니다.', description: '방송이 재개되면 댓글과 활동이 여기에 표시됩니다.',
    label: '방송 일시정지', tone: 'waiting'
  },
  ended: {
    title: '방송이 종료되었습니다.', description: '새 방송이 시작되면 자동으로 연결합니다.',
    label: '방송 종료', tone: 'neutral'
  },
  listening: {
    title: '첫 댓글을 기다리고 있어요.', description: '댓글과 활동이 도착하면 여기에 표시됩니다.',
    label: '방송 중', tone: 'live'
  }
} as const;

export interface MonitorView {
  kind: keyof typeof views;
  title: string;
  description: string;
  label: string;
  tone: 'neutral' | 'waiting' | 'live' | 'error';
}

export function monitorView(backend: BackendState, source: StatusMessage | null): MonitorView {
  let kind: MonitorView['kind'];
  if (backend === 'connecting') kind = 'server-connecting';
  else if (backend === 'disconnected') kind = 'server-disconnected';
  else if (!source) kind = 'checking';
  else if (source.state === 'idle') kind = 'idle';
  else if (source.state === 'error') kind = 'error';
  else if (source.live?.state === 'ended') kind = 'ended';
  else if (source.state !== 'connected') kind = source.state;
  else if (source.live?.state === 'paused') kind = 'paused';
  else kind = 'listening';

  const view: MonitorView = { kind, ...views[kind] };
  if (kind === 'error' && source?.message.trim()) view.description = source.message;
  if (kind === 'listening' && source?.live?.state !== 'live') {
    view.label = '방송 상태 확인 중';
    view.tone = 'neutral';
  }
  return view;
}
