<script lang="ts">
    let { username }: { username: string | null } = $props();
    let feedback = $state<'copied' | 'error' | null>(null);
    let busy = $state(false);
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

<div class="broadcast-account" data-feedback={feedback}>
    {#if username}
        <button
            type="button"
            class="account-copy"
            onclick={copyAccount}
            disabled={busy}
            aria-label="방송 아이디 복사"
            title={`@${username} · ${label}`}
        >
            <span class="account-name">@{username}</span>
            <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
            >
                {#if feedback === 'copied'}
                    <path d="m5 12 4 4L19 6" />
                {:else}
                    <path d="M8 8h12v13H8zM16 8V3H3v13h5" />
                {/if}
            </svg>
        </button>
    {:else}
        <span class="demo-label">DEMO</span>
    {/if}
    <span class="copy-feedback" role="status">{feedback ? label : ''}</span>
</div>

<style>
    .account-name {
        display: block;
        min-width: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .broadcast-account {
        position: relative;
        min-width: 0;
        max-width: 100%;
    }
    .account-copy {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        min-width: 0;
        max-width: 100%;
        min-height: 44px;
        padding: 0;
        border: 0;
        background: none;
        color: var(--m3c-on-surface);
        font: inherit;
        font-size: 0.95rem;
        font-weight: 750;
        cursor: pointer;
    }
    .account-copy:hover .account-name {
        text-decoration: underline;
        text-underline-offset: 0.2em;
    }
    .account-copy:focus-visible {
        outline: 2px solid var(--m3c-secondary);
        outline-offset: 4px;
    }
    .account-copy:disabled {
        opacity: 0.5;
        cursor: wait;
    }
    .account-copy svg {
        flex-shrink: 0;
        width: 16px;
        height: 16px;
        color: var(--m3c-on-surface-variant);
    }
    .demo-label {
        display: inline-flex;
        align-items: center;
        min-height: 44px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        color: var(--m3c-secondary);
    }
    .copy-feedback {
        position: absolute;
        top: 100%;
        left: 0;
        z-index: 2;
        font-size: 0.7rem;
        white-space: nowrap;
        color: var(--m3c-secondary);
    }
    [data-feedback='error'] .copy-feedback {
        color: var(--m3c-error);
        white-space: normal;
        width: max-content;
        max-width: min(280px, 80vw);
    }
</style>
