export type SourceState = 'connecting' | 'connected' | 'waiting' | 'disconnected' | 'error';
export type Source = 'tiktok' | 'mock';
export interface CommentMessage {
  type: 'comment';
  id: string;
  received_at: string;
  user: { nickname: string; unique_id: string };
  comment: string;
}
export interface StatusMessage {
  type: 'status';
  source: Source;
  state: SourceState;
  message: string;
}
export type Message = CommentMessage | StatusMessage;
export type BackendState = 'connecting' | 'connected' | 'disconnected';

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function parseMessage(raw: unknown): Message | null {
  if (typeof raw !== 'string') return null;
  let value: unknown;
  try { value = JSON.parse(raw); } catch { return null; }
  if (!record(value)) return null;
  if (value.type === 'comment' && typeof value.id === 'string' && value.id.length > 0 &&
      typeof value.received_at === 'string' && Number.isFinite(Date.parse(value.received_at)) &&
      record(value.user) && typeof value.user.nickname === 'string' &&
      typeof value.user.unique_id === 'string' && typeof value.comment === 'string' &&
      value.comment.trim().length > 0) return value as unknown as CommentMessage;
  if (value.type === 'status' && ['mock', 'tiktok'].includes(String(value.source)) &&
      ['connecting', 'connected', 'waiting', 'disconnected', 'error'].includes(String(value.state)) &&
      typeof value.message === 'string') return value as unknown as StatusMessage;
  return null;
}
