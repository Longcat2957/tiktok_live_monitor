<script lang="ts">
    import { Button } from 'm3-svelte';
    import type { StatusMessage } from '$lib/types';

    let {
        actionError,
        source,
        recoveryMessage,
        pending,
        checking,
        oncheck,
    }: {
        actionError: string;
        source: StatusMessage | null;
        recoveryMessage: string;
        pending: boolean;
        checking: boolean;
        oncheck: () => void;
    } = $props();
</script>

{#if actionError}<p class="action-error" role="alert">{actionError}</p>
{:else if source?.state === 'error'}<p class="action-error" role="status">{source.message}</p>{/if}
{#if recoveryMessage}
    <div class="recovery-notice">
        <p role="status">{recoveryMessage}</p>
        {#if pending}<Button variant="text" size="s" disabled={checking} onclick={oncheck}
                >{checking ? '확인 중…' : '상태 다시 확인'}</Button
            >{/if}
    </div>
{/if}

<style>
    .action-error {
        color: var(--m3c-error);
        font-size: 0.85rem;
        margin: 0;
    }
    .recovery-notice {
        flex-shrink: 0;
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
        font-size: 0.8rem;
        color: var(--monitor-waiting);
    }
    .recovery-notice p {
        margin: 0;
    }
</style>
