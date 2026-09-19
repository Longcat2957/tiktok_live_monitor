import { requestJson } from '../api';
import { parseMessage, type Source, type StatusMessage } from '../types';

export class MonitorCommands {
    saving = $state(false);
    checking = $state(false);
    pendingSession = $state<string | null>(null);
    recoveryMessage = $state('');
    actionError = $state('');
    private requests = new AbortController();
    private timer: ReturnType<typeof setTimeout> | undefined;
    private actionSession: string | null = null;

    constructor(private getSource: () => StatusMessage | null) {}

    get blocked(): boolean {
        return this.saving || this.pendingSession !== null;
    }

    async start(mode: Source, account: string): Promise<string | null> {
        const source = this.getSource();
        if (!source) return null;
        return this.sendChange(
            '/account',
            'POST',
            { source: mode, username: mode === 'tiktok' ? account : '' },
            source.session_id,
        );
    }

    async stop(): Promise<string | null> {
        return this.updateMonitor(false);
    }
    async refresh(): Promise<string | null> {
        return this.updateMonitor(true);
    }

    async updateSettings(
        settings: Record<string, unknown>,
        expected: string,
    ): Promise<string | null> {
        return this.sendChange('/config', 'PATCH', { settings }, expected);
    }

    acceptStatus(status: StatusMessage): void {
        if (this.actionSession && status.session_id !== this.actionSession) {
            this.actionSession = null;
            this.actionError = '';
        }
        if (this.pendingSession && status.session_id !== this.pendingSession) {
            this.pendingSession = null;
            this.actionError = '';
            this.recoveryMessage = '서버의 상태 변경을 확인했습니다. 현재 화면에 반영했습니다.';
            this.scheduleCheck();
        }
    }

    async checkResult(): Promise<void> {
        if (!this.pendingSession || this.checking || this.requests.signal.aborted) return;
        const expected = this.pendingSession;
        this.checking = true;
        this.scheduleCheck();
        try {
            const { data } = await requestJson(
                '/health',
                { signal: this.requests.signal, cache: 'no-store' },
                5000,
            );
            if (
                typeof data !== 'object' ||
                data === null ||
                !('source' in data) ||
                !('pending_commands' in data) ||
                !Number.isInteger(data.pending_commands) ||
                Number(data.pending_commands) < 0
            )
                throw new Error('Invalid server status');
            const snapshot = parseMessage(JSON.stringify(data.source));
            if (snapshot?.type !== 'status') throw new Error('Invalid server status');
            if (this.pendingSession !== expected) return;
            if (snapshot.session_id !== expected || data.pending_commands === 0) {
                this.pendingSession = null;
                this.recoveryMessage =
                    snapshot.session_id !== expected
                        ? '서버의 상태 변경을 확인했습니다. 현재 화면을 확인해주세요.'
                        : '서버가 현재 처리 중인 요청은 없습니다. 상태 변경이 필요하면 다시 시도해주세요.';
            } else {
                this.recoveryMessage =
                    '서버에서 요청을 처리 중입니다. 완료될 때까지 중복 요청을 보내지 않습니다.';
            }
            // WebSocket alone applies session boundaries; HTTP snapshots only resolve requests.
        } catch {
            if (!this.requests.signal.aborted && this.pendingSession === expected)
                this.recoveryMessage =
                    '처리 결과를 확인할 수 없습니다. 연결이 복구되면 자동으로 다시 확인합니다.';
        } finally {
            this.checking = false;
            this.scheduleCheck();
        }
    }

    dispose(): void {
        this.requests.abort();
        clearTimeout(this.timer);
        this.timer = undefined;
    }

    private scheduleCheck(): void {
        clearTimeout(this.timer);
        this.timer = undefined;
        if (
            this.pendingSession &&
            !this.checking &&
            !this.saving &&
            !this.requests.signal.aborted
        ) {
            this.timer = setTimeout(() => {
                this.timer = undefined;
                void this.checkResult();
            }, 3000);
        }
    }

    private async sendChange(
        path: string,
        method: string,
        body: Record<string, unknown>,
        expected: string,
    ): Promise<string | null> {
        if (this.blocked) return '이전 요청의 처리 결과를 확인하고 있습니다.';
        this.saving = true;
        this.recoveryMessage = '';
        try {
            const response = await requestJson(path, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: expected, ...body }),
                signal: this.requests.signal,
            });
            if (response.status === 409)
                return '다른 화면에서 상태가 변경되었습니다. 현재 상태를 확인하고 다시 시도해주세요.';
            if (response.status === 422) return '@아이디 또는 설정값의 허용 범위를 확인해주세요.';
            if (response.status >= 500) throw new Error('Server response uncertain');
            if (!response.ok)
                return '요청을 처리하지 못했습니다. 서버 상태를 확인하고 다시 시도해주세요.';
            return null;
        } catch {
            if (this.requests.signal.aborted) return '화면이 닫혀 요청 결과를 확인하지 못했습니다.';
            const source = this.getSource();
            if (source && source.session_id !== expected) {
                this.recoveryMessage = '서버의 상태 변경을 확인했습니다. 현재 화면에 반영했습니다.';
                return '요청 응답을 받지 못했지만 서버의 현재 상태를 확인했습니다.';
            }
            this.pendingSession = expected;
            this.recoveryMessage = '요청 응답이 지연되어 처리 결과를 확인 중입니다…';
            await this.checkResult();
            return '요청 응답을 받지 못했습니다. 서버 상태 확인 안내를 참고해주세요.';
        } finally {
            this.saving = false;
            this.scheduleCheck();
        }
    }

    private async updateMonitor(refresh: boolean): Promise<string | null> {
        const source = this.getSource();
        if (!source || source.state === 'idle' || this.blocked) return null;
        this.actionSession = source.session_id;
        this.actionError = '';
        const problem = await this.sendChange(
            refresh ? '/refresh' : '/account',
            refresh ? 'POST' : 'DELETE',
            {},
            source.session_id,
        );
        if (problem && this.getSource()?.session_id === source.session_id) {
            this.actionError = this.recoveryMessage
                ? problem
                : (refresh ? '새로고침하지 못했습니다. ' : '초기화하지 못했습니다. ') + problem;
        }
        return problem;
    }
}
