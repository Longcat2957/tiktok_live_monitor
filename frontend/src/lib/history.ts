import type { FeedMessage } from './types';

export function appendComment<T extends FeedMessage>(history: T[], comment: T, limit: number): T[] {
    if (history.some((item) => item.id === comment.id)) return history;
    let remove = Math.max(
        0,
        history.filter((item) => item.platform === comment.platform).length +
            1 -
            Math.max(1, limit),
    );
    return [
        ...history.filter((item) => {
            if (item.platform !== comment.platform || remove === 0) return true;
            remove--;
            return false;
        }),
        comment,
    ];
}
