<script lang="ts">
    import FontScaleControl from './FontScaleControl.svelte';
    import ThemeToggle from './ThemeToggle.svelte';
    import ToolbarButton from './ToolbarButton.svelte';

    let {
        active,
        blocked,
        fontScale = $bindable(100),
        onsettings,
        onrefresh,
        onstop,
    }: {
        active: boolean;
        blocked: boolean;
        fontScale: number;
        onsettings: () => void;
        onrefresh: () => void;
        onstop: () => void;
    } = $props();
    let title: HTMLDivElement;

    export function focus() {
        title?.focus({ preventScroll: true });
    }
</script>

<header class="monitor-header">
    <div class="wordmark" id="monitor-title" tabindex="-1" bind:this={title}>
        <span class="live-badge">LIVE</span><span>댓글 모니터</span>
    </div>
    {#if active}
        <div class="monitor-actions">
            <FontScaleControl bind:value={fontScale} />
            <ThemeToggle />
            <ToolbarButton label="모니터 설정" disabled={blocked} onclick={onsettings}>
                <svg
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                >
                    <path d="M4 7h9m4 0h3M4 17h3m4 0h9" /><circle cx="15" cy="7" r="2" /><circle
                        cx="9"
                        cy="17"
                        r="2"
                    />
                </svg>
            </ToolbarButton>
            <ToolbarButton label="댓글 비우기 · 다시 연결" disabled={blocked} onclick={onrefresh}>
                <svg
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                >
                    <path d="M21 10a9 9 0 1 0-2 8M21 4v6h-6" />
                </svg>
            </ToolbarButton>
            <ToolbarButton label="모니터 종료 · 처음으로" disabled={blocked} onclick={onstop}>
                <svg
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                >
                    <path d="M9 4H4v16h5M9 12h12m-4-4 4 4-4 4" />
                </svg>
            </ToolbarButton>
        </div>
    {:else}<div class="monitor-actions">
            <span class="header-note">YOUR LIVE. EVERY COMMENT.</span><ThemeToggle />
        </div>{/if}
</header>

<style>
    .monitor-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 16px;
        flex-shrink: 0;
        padding-bottom: 24px;
        border-bottom: 1px solid var(--m3c-outline-variant);
    }
    .monitor-actions {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        justify-content: flex-end;
        gap: 12px;
    }
    .wordmark {
        display: flex;
        align-items: center;
        gap: 14px;
        font-size: 1rem;
        font-weight: 750;
    }
    .live-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 5px;
        padding: 5px 9px;
        font-size: 0.7rem;
        font-weight: 850;
        letter-spacing: 0.08em;
        background: var(--m3c-primary);
        color: var(--m3c-on-primary);
        box-shadow: -3px 3px 0 var(--m3c-secondary);
    }
    .header-note {
        font-size: 0.6rem;
        letter-spacing: 0.12em;
        color: var(--m3c-on-surface-variant);
    }
    @media (width < 480px) {
        .header-note {
            display: none;
        }
    }
</style>
