export type SourceState =
    'idle' | 'connecting' | 'connected' | 'waiting' | 'disconnected' | 'error';
export type Source = 'tiktok' | 'mock';
export interface UserBadge {
    kind: 'subscriber' | 'fan';
    level: number | null;
}
export interface Viewer {
    nickname: string;
    unique_id: string;
    avatar_url?: string | null;
    badges?: UserBadge[];
}
export interface LiveInfo {
    state: 'unknown' | 'live' | 'paused' | 'ended';
    viewers: number | null;
    likes: number | null;
}
export interface CommentMessage {
    type: 'comment';
    id: string;
    received_at: string;
    user: Viewer;
    comment: string;
}
export interface ActivityMessage {
    type: 'activity';
    id: string;
    received_at: string;
    user: Viewer;
    kind: 'gift' | 'follow' | 'share' | 'subscribe';
    gift_name: string;
    count: number;
}
export type FeedMessage = CommentMessage | ActivityMessage;
export interface StatusMessage {
    type: 'status';
    live?: LiveInfo;
    source: Source;
    state: SourceState;
    message: string;
    session_id: string;
    username: string | null;
    comment_history_size: number;
}
export type Message = FeedMessage | StatusMessage;
export type BackendState = 'connecting' | 'connected' | 'disconnected';

function record(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringWithinLimit(value: unknown, limit: number): value is string {
    // Python/Pydantic count Unicode code points, while JS length counts UTF-16 units.
    return typeof value === 'string' && (value.length <= limit || [...value].length <= limit);
}

export function safeAvatar(value: unknown): value is string {
    if (!stringWithinLimit(value, 2048)) return false;
    if (/^\/demo-avatar-[0-2]\.svg$/.test(value)) return true;
    try {
        const url = new URL(value);
        return url.protocol === 'https:' && Boolean(url.hostname) && !url.username && !url.password;
    } catch {
        return false;
    }
}

function parseUser(value: unknown): Viewer | null {
    if (
        !record(value) ||
        !stringWithinLimit(value.nickname, 256) ||
        !stringWithinLimit(value.unique_id, 256)
    )
        return null;
    const user: Viewer = { nickname: value.nickname, unique_id: value.unique_id };
    if (value.avatar_url === null || safeAvatar(value.avatar_url))
        user.avatar_url = value.avatar_url;
    if (Array.isArray(value.badges)) {
        user.badges = [];
        for (const badge of value.badges) {
            if (
                !record(badge) ||
                (badge.kind !== 'subscriber' && badge.kind !== 'fan') ||
                !(
                    badge.level === null ||
                    (typeof badge.level === 'number' &&
                        Number.isInteger(badge.level) &&
                        badge.level >= 0 &&
                        badge.level <= 10000)
                ) ||
                user.badges.some((item) => item.kind === badge.kind)
            )
                continue;
            user.badges.push({ kind: badge.kind, level: badge.level });
            if (user.badges.length === 2) break;
        }
    }
    return user;
}

function validLive(value: unknown): boolean {
    return (
        value === undefined ||
        (record(value) &&
            typeof value.state === 'string' &&
            ['unknown', 'live', 'paused', 'ended'].includes(value.state) &&
            [value.viewers, value.likes].every(
                (n) => n === null || (Number.isSafeInteger(n) && Number(n) >= 0),
            ))
    );
}

export function parseMessage(raw: unknown): Message | null {
    if (typeof raw !== 'string') return null;
    let value: unknown;
    try {
        value = JSON.parse(raw);
    } catch {
        return null;
    }
    if (!record(value)) return null;
    if (
        (value.type === 'comment' || value.type === 'activity') &&
        typeof value.id === 'string' &&
        value.id.length > 0 &&
        typeof value.received_at === 'string' &&
        Number.isFinite(Date.parse(value.received_at))
    ) {
        const user = parseUser(value.user);
        if (!user) return null;
        if (
            value.type === 'comment' &&
            stringWithinLimit(value.comment, 10000) &&
            value.comment.trim().length > 0
        )
            return { ...value, user } as unknown as CommentMessage;
        if (
            value.type === 'activity' &&
            typeof value.kind === 'string' &&
            ['gift', 'follow', 'share', 'subscribe'].includes(value.kind) &&
            stringWithinLimit(value.gift_name, 256) &&
            Number.isInteger(value.count) &&
            Number(value.count) >= 1 &&
            Number(value.count) <= 1_000_000_000
        )
            return { ...value, user } as unknown as ActivityMessage;
    }
    if (
        value.type === 'status' &&
        (value.source === 'mock' || value.source === 'tiktok') &&
        typeof value.state === 'string' &&
        ['idle', 'connecting', 'connected', 'waiting', 'disconnected', 'error'].includes(
            value.state,
        ) &&
        typeof value.message === 'string' &&
        typeof value.session_id === 'string' &&
        Number.isInteger(value.comment_history_size) &&
        Number(value.comment_history_size) >= 1 &&
        Number(value.comment_history_size) <= 1000 &&
        validLive(value.live) &&
        value.session_id.length > 0 &&
        (value.username === null || typeof value.username === 'string')
    )
        return value as unknown as StatusMessage;
    return null;
}
