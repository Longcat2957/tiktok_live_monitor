import type { FeedMessage } from './types';

export function appendComment<T extends FeedMessage>(history: T[], comment: T, limit: number): T[] {
  if (history.some((item) => item.id === comment.id)) return history;
  return [...history, comment].slice(-Math.max(1, limit));
}
