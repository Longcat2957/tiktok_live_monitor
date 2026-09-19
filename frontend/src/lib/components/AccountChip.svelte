<script lang="ts">
    import { Chip } from 'm3-svelte';
    let { username }: { username: string | null } = $props();
    let feedback = $state<'copied' | 'error' | null>(null);
    let busy = $state(false);
    const copyIcon = {
        width: 24,
        height: 24,
        body: '<path fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" d="M8 8h12v13H8zM16 8V3H3v13h5"/>',
    };
    const checkIcon = {
        width: 24,
        height: 24,
        body: '<path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="m5 12 4 4L19 6"/>',
    };
    let label = $derived(
        feedback === 'copied'
            ? '아이디 복사됨'
            : feedback === 'error'
              ? '복사하지 못했습니다. 다시 시도해주세요.'
              : '방송 아이디 복사',
    );
    $effect(() => {
        if (feedback) {
            const timer = setTimeout(() => (feedback = null), 2500);
            return () => clearTimeout(timer);
        }
    });
    async function copyAccount() {
        if (!username || busy) return;
        busy = true;
        try {
            await navigator.clipboard.writeText(`@${username}`);
            feedback = 'copied';
        } catch {
            feedback = 'error';
        } finally {
            busy = false;
        }
    }
</script>

<div class="account-chip" data-feedback={feedback}>
    {#if username}
        <Chip
            variant="assist"
            trailingIcon={feedback === 'copied' ? checkIcon : copyIcon}
            onclick={copyAccount}
            disabled={busy}
            aria-label="방송 아이디 복사"
            title={`${'@' + username} · ${label}`}
        >
            <span class="account-name">@{username}</span>
        </Chip>
    {:else}
        <span class="demo-chip">DEMO</span>
    {/if}
    <span class="copy-feedback" role="status">{feedback ? label : ''}</span>
</div>

<style>
    .account-name {
        min-width: 0;
        margin: 0;
        font-weight: 700;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .account-chip {
        position: relative;
        min-width: 0;
        max-width: 100%;
        --m3-chip-shape: 999px;
    }
    .account-chip :global(button),
    .demo-chip {
        max-width: 100%;
        min-height: 44px;
        padding-inline: 14px;
        background: var(--m3c-secondary-container);
        color: var(--m3c-on-secondary-container);
        border: 1px solid var(--m3c-secondary);
        border-radius: 999px;
        font-weight: 700;
    }
    .account-chip :global(button > span) {
        min-width: 0;
        overflow: hidden;
    }
    .account-chip :global(svg) {
        flex-shrink: 0;
    }
    .account-name {
        display: block;
    }
    .demo-chip {
        display: inline-flex;
        align-items: center;
    }
    .copy-feedback {
        position: absolute;
        top: 100%;
        left: 0;
        z-index: 2;
        font-size: 0.7rem;
        white-space: nowrap;
    }
    .copy-feedback:not(:empty) {
        padding: 4px 8px;
        border-radius: 6px;
        background: var(--m3c-secondary-container);
        color: var(--m3c-on-secondary-container);
    }
    [data-feedback='error'] .copy-feedback {
        background: var(--m3c-error-container);
        color: var(--m3c-on-error-container);
        white-space: normal;
        width: max-content;
        max-width: min(280px, 80vw);
    }
</style>
