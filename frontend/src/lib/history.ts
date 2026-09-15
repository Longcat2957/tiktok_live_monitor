import type { CommentMessage } from './types';

export function appendComment(history: CommentMessage[], comment: CommentMessage, limit: number): CommentMessage[] {
  if (history.some((item) => item.id === comment.id)) return history;
  return [...history, comment].slice(-Math.max(1, limit));
}
