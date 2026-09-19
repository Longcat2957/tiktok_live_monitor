<script lang="ts">
    import type { BackendState } from '../types';
    let { backend }: { backend: BackendState } = $props();
    let message = $derived(
        backend === 'connected'
            ? '서버 연결됨'
            : backend === 'connecting'
              ? '서버 연결중'
              : '서버 연결실패',
    );
</script>

<div class="connection" role="status" data-state={backend}>
    <span class="status-dot" aria-hidden="true"></span>
    <span>{message}</span>
</div>

<style>
    .connection {
        display: flex;
        align-items: center;
        flex-shrink: 0;
        white-space: nowrap;
        gap: 10px;
        font-size: clamp(12px, 1.7vw, 20px);
        color: var(--m3c-on-surface-variant);
        overflow-wrap: anywhere;
    }
    .status-dot {
        width: 8px;
        height: 8px;
        flex-shrink: 0;
        border-radius: 50%;
        background: var(--monitor-waiting);
    }
    .connection[data-state='connected'] .status-dot {
        background: var(--m3c-secondary);
    }
    .connection[data-state='disconnected'] .status-dot {
        background: var(--m3c-error);
    }
</style>
