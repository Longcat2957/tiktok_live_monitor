import { RECONNECT_MIN_MS, RECONNECT_MAX_MS } from './config';
import { parseMessage, type BackendState, type Message } from './types';

export function websocketUrl(location: Pick<Location, 'protocol' | 'host'>): string {
    return `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`;
}

export function connectMonitor(
    url: string,
    onMessage: (message: Message) => void,
    onState: (state: BackendState) => void,
): () => void {
    let stopped = false;
    let socket: WebSocket | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = RECONNECT_MIN_MS;
    function retry() {
        if (stopped) return;
        onState('disconnected');
        timer = setTimeout(connect, delay);
        delay = Math.min(delay * 2, RECONNECT_MAX_MS);
    }
    function connect() {
        if (stopped) return;
        onState('connecting');
        try {
            socket = new WebSocket(url);
        } catch {
            retry();
            return;
        }
        socket.onopen = () => {
            if (stopped) return;
            delay = RECONNECT_MIN_MS;
            onState('connected');
        };
        socket.onmessage = (event) => {
            if (stopped) return;
            const message = parseMessage(event.data);
            if (message) onMessage(message);
        };
        socket.onerror = () => socket?.close();
        socket.onclose = retry;
    }
    connect();
    return () => {
        stopped = true;
        clearTimeout(timer);
        if (socket) {
            socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
            socket.close();
        }
    };
}
