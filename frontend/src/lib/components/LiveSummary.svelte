<script lang="ts">
    import BroadcastAccount from './BroadcastAccount.svelte';
    import type { BackendState, Platform, StatusMessage } from '$lib/types';

    let {
        source,
        backend,
        platform = 'tiktok',
    }: { source: StatusMessage; backend: BackendState; platform?: Platform } = $props();
    let status = $derived(platform === 'tiktok' ? source : source.youtube);
    let live = $derived(status?.live);
    let name = $derived(platform === 'tiktok' ? 'TikTok' : 'YouTube');
    const number = new Intl.NumberFormat('ko-KR');
</script>

<section class="live-summary" data-platform={platform} aria-label={`${name} 방송 정보`}>
    {#if source.source === 'mock'}
        <span class="demo-label">DEMO</span>
    {:else if platform === 'tiktok'}
        {#key source.username}<BroadcastAccount username={source.username} />{/key}
    {/if}
    <dl
        class="live-metrics"
        aria-label={`${name} 방송 통계`}
        class:stale={backend !== 'connected' || status?.state !== 'connected'}
    >
        <div class="live-metric">
            <dt>
                <svg
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                >
                    <circle cx="9" cy="8" r="3" />
                    <path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v2" />
                </svg>
                시청자
            </dt>
            <dd title={live?.viewers == null ? '제공되지 않음' : undefined}>
                <strong>{live?.viewers == null ? '—' : number.format(live.viewers)}</strong>
            </dd>
        </div>
        <div class="live-metric likes">
            <dt>
                <svg
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                >
                    <path
                        d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"
                    />
                </svg>
                좋아요
            </dt>
            <dd title={live?.likes == null ? '제공되지 않음' : undefined}>
                <strong>{live?.likes == null ? '—' : number.format(live.likes)}</strong>
            </dd>
        </div>
    </dl>
</section>

<style>
    .live-summary {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 4px 12px;
        flex-shrink: 0;
        font-size: 0.8rem;
    }
    .demo-label {
        display: inline-flex;
        align-items: center;
        font-size: 0.6rem;
        font-weight: 750;
        color: var(--m3c-on-secondary-container);
        background: var(--m3c-secondary-container);
        border-radius: 4px;
        padding: 4px 8px;
    }
    .live-metrics {
        display: flex;
        flex-wrap: wrap;
        justify-content: flex-end;
        align-items: center;
        min-width: 0;
        max-width: 100%;
        margin: 0;
        gap: 4px 10px;
        color: var(--m3c-on-surface-variant);
        font-variant-numeric: tabular-nums;
        margin-inline-start: auto;
    }
    .live-metric {
        display: flex;
        align-items: center;
        min-width: 0;
        gap: 6px;
    }
    .live-metric + .live-metric {
        padding-inline-start: 10px;
        border-inline-start: 1px solid var(--m3c-outline-variant);
    }
    .live-metric svg {
        flex-shrink: 0;
        width: 16px;
        height: 16px;
        color: var(--m3c-secondary);
    }
    .likes svg {
        color: var(--m3c-primary);
    }
    dt {
        display: flex;
        align-items: center;
        flex-shrink: 0;
        gap: 6px;
        font-size: 0.75rem;
        line-height: 1.4;
    }
    dd {
        min-width: 0;
        margin: 0;
        overflow-wrap: anywhere;
        font-size: 1rem;
        line-height: 1.2;
        color: var(--m3c-on-surface);
    }
    .live-metrics.stale {
        opacity: 0.5;
    }
</style>
