<script lang="ts">
    import BroadcastAccount from './BroadcastAccount.svelte';
    import type { BackendState, StatusMessage } from '$lib/types';

    let { source, backend }: { source: StatusMessage; backend: BackendState } = $props();
    const number = new Intl.NumberFormat('ko-KR');
</script>

<section class="live-summary" aria-label="방송 정보">
    {#key source.username}<BroadcastAccount username={source.username} />{/key}
    <dl
        class="live-metrics"
        aria-label="방송 통계"
        class:stale={backend !== 'connected' || source.state !== 'connected'}
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
            <dd>
                <strong
                    >{source.live?.viewers == null
                        ? '—'
                        : number.format(source.live.viewers)}</strong
                >
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
            <dd>
                <strong
                    >{source.live?.likes == null ? '—' : number.format(source.live.likes)}</strong
                >
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
        gap: 12px 20px;
        flex-shrink: 0;
        margin-bottom: -16px;
        font-size: 0.8rem;
    }
    .live-metrics {
        display: flex;
        align-items: center;
        min-width: 0;
        margin: 0;
        gap: 16px;
        color: var(--m3c-on-surface-variant);
        font-variant-numeric: tabular-nums;
    }
    .live-metric {
        display: flex;
        align-items: center;
        min-width: 0;
        gap: 8px;
    }
    .live-metric + .live-metric {
        padding-inline-start: 16px;
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
        font-size: 1.25rem;
        line-height: 1.2;
        color: var(--m3c-on-surface);
    }
    .live-metrics.stale {
        opacity: 0.5;
    }
</style>
