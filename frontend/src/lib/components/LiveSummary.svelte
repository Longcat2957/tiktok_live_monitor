<script lang="ts">
    import AccountChip from './AccountChip.svelte';
    import type { BackendState, StatusMessage } from '$lib/types';

    let { source, backend }: { source: StatusMessage; backend: BackendState } = $props();
    const number = new Intl.NumberFormat('ko-KR');
</script>

<section class="live-summary" aria-label="방송 정보">
    {#key source.username}<AccountChip username={source.username} />{/key}
    <div
        class="live-metrics"
        aria-label="방송 통계"
        class:stale={backend !== 'connected' || source.state !== 'connected'}
    >
        <span
            >시청자 <strong
                >{source.live?.viewers == null ? '—' : number.format(source.live.viewers)}</strong
            ></span
        >
        <span
            >좋아요 <strong
                >{source.live?.likes == null ? '—' : number.format(source.live.likes)}</strong
            ></span
        >
    </div>
</section>

<style>
    .live-summary {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 8px 20px;
        flex-shrink: 0;
        font-size: 0.8rem;
    }
    .live-metrics {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        color: var(--m3c-on-surface-variant);
        font-variant-numeric: tabular-nums;
    }
    .live-metrics strong {
        color: var(--m3c-on-surface);
        margin-left: 4px;
    }
    .live-metrics.stale {
        opacity: 0.5;
    }
</style>
