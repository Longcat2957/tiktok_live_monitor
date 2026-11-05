<script lang="ts">
    import { Button, ConnectedButtons } from 'm3-svelte';
    import type { FeedLayout } from '$lib/types';
    import FontScaleControl from './FontScaleControl.svelte';
    import ThemeToggle from './ThemeToggle.svelte';
    import ToolbarButton from './ToolbarButton.svelte';

    let {
        active,
        blocked,
        fontScale = $bindable(100),
        layout = $bindable('split'),
        onsettings,
        onrefresh,
        onstop,
    }: {
        active: boolean;
        blocked: boolean;
        fontScale: number;
        layout: FeedLayout;
        onsettings: () => void;
        onrefresh: () => void;
        onstop: () => void;
    } = $props();
    let title = $state<HTMLElement>();
    const layouts = [
        { value: 'split', label: '상하 분할' },
        { value: 'side-by-side', label: '좌우 분할' },
        { value: 'combined', label: '통합' },
        { value: 'tiktok', label: 'TikTok' },
        { value: 'youtube', label: 'YouTube' },
    ];
    let layoutLabel = $derived(layouts.find((option) => option.value === layout)?.label);

    export function focus() {
        title?.focus({ preventScroll: true });
    }
</script>

<header class="monitor-header">
    {#if active}
        <details class="view-options">
            <summary id="monitor-title" aria-label={`댓글 보기: ${layoutLabel}`} bind:this={title}>
                <strong>{layoutLabel}</strong>
                <svg
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                >
                    <path d="m6 9 6 6 6-6" />
                </svg>
            </summary>
            <fieldset class="view-controls">
                <legend>댓글 보기</legend>
                <ConnectedButtons>
                    {#each layouts as option (option.value)}
                        <Button variant="tonal" size="s" square label>
                            <input
                                type="radio"
                                name="feed-view"
                                value={option.value}
                                bind:group={layout}
                            />
                            {option.label}
                        </Button>
                    {/each}
                </ConnectedButtons>
            </fieldset>
        </details>
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
    {:else}
        <div class="wordmark" id="monitor-title" tabindex="-1" bind:this={title}>
            <span class="live-badge">LIVE</span><span>댓글 모니터</span>
        </div>
        <div class="monitor-actions">
            <span class="header-note">YOUR LIVE. EVERY COMMENT.</span><ThemeToggle />
        </div>{/if}
</header>

<style>
    .monitor-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 6px 12px;
        flex-shrink: 0;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--m3c-outline-variant);
    }
    .monitor-actions {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        justify-content: flex-end;
        gap: 6px;
    }
    .view-options {
        position: relative;
        flex-shrink: 0;
    }
    summary {
        display: flex;
        align-items: center;
        gap: 8px;
        min-height: 44px;
        cursor: pointer;
        list-style: none;
        font-size: 0.75rem;
        color: var(--m3c-on-surface-variant);
    }
    summary::-webkit-details-marker {
        display: none;
    }
    summary strong {
        color: var(--m3c-on-surface);
    }
    summary svg {
        width: 18px;
        height: 18px;
    }
    .view-options[open] summary svg {
        transform: rotate(180deg);
    }
    summary:focus-visible {
        outline: 2px solid var(--m3c-secondary);
        outline-offset: 3px;
        border-radius: 4px;
    }
    .view-controls {
        position: absolute;
        top: calc(100% + 6px);
        left: 0;
        z-index: 3;
        width: 400px;
        min-width: 0;
        max-width: calc(100vw - 24px);
        margin: 0;
        padding: 8px;
        border: 1px solid var(--m3c-outline-variant);
        border-radius: 12px;
        background: var(--m3c-surface-container-high);
        box-shadow: 0 4px 12px #0004;
    }
    .view-controls :global(.m3-container) {
        min-width: 0;
    }
    .view-controls :global(label.m3-container) {
        min-height: 44px;
        padding-inline: 6px;
        font-size: 14px;
        white-space: nowrap;
    }
    legend {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip-path: inset(50%);
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
        .view-controls > :global(div) {
            grid-auto-flow: row;
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .monitor-actions {
            display: contents;
        }
        .header-note {
            display: none;
        }
    }
</style>
