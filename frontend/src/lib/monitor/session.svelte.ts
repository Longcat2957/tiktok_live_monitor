import { DEFAULT_HISTORY_SIZE } from '../config';
import { appendComment } from '../history';
import { connectMonitor, websocketUrl } from '../websocket';
import type { BackendState, FeedMessage, StatusMessage } from '../types';

export class MonitorSession {
    comments = $state<FeedMessage[]>([]);
    backend = $state<BackendState>('connecting');
    source = $state<StatusMessage | null>(null);

    connect(onStatus: (status: StatusMessage) => void): () => void {
        let limit = DEFAULT_HISTORY_SIZE;
        let pending: FeedMessage[] = [];
        let frame: number | undefined;
        function clearPending() {
            if (frame !== undefined) cancelAnimationFrame(frame);
            frame = undefined;
            pending = [];
        }
        const disconnect = connectMonitor(
            websocketUrl(window.location),
            (message) => {
                if (message.type !== 'status') {
                    // Bound the waiting batch too: hidden tabs can suspend animation frames.
                    pending = appendComment(pending, message, limit);
                    frame ??= requestAnimationFrame(() => {
                        frame = undefined;
                        this.comments = pending.reduce(
                            (history, item) => appendComment(history, item, limit),
                            this.comments,
                        );
                        pending = [];
                    });
                } else {
                    limit = message.comment_history_size;
                    if (this.source?.session_id !== message.session_id) {
                        clearPending();
                        this.comments = [];
                    }
                    this.source = message;
                    onStatus(message);
                }
            },
            (state) => {
                this.backend = state;
            },
        );
        return () => {
            clearPending();
            disconnect();
        };
    }
}
