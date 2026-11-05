<script lang="ts">
    import type { Platform } from '$lib/types';

    let { platform }: { platform: Platform } = $props();
</script>

<span class="platform-badge" data-platform={platform}>
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
        {#if platform === 'tiktok'}
            <path
                d="M14 3h3c.2 2.4 1.6 4.1 4 4.4v3a9 9 0 0 1-4-1.3V16a6 6 0 1 1-6-6v3a3 3 0 1 0 3 3Z"
            />
        {:else}
            <path d="m8 5 12 7-12 7Z" />
        {/if}
    </svg>
    <span>{platform === 'tiktok' ? 'TikTok' : 'YouTube'}</span>
</span>

<style>
    .platform-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35em;
        padding: 0.25em 0.5em;
        border: 1px solid #25f4ee;
        border-radius: 0.3em;
        background: #101114;
        color: #fff;
        font-weight: 800;
        line-height: 1.25;
        white-space: nowrap;
    }
    .platform-badge[data-platform='youtube'] {
        background: #c20e26;
        border-color: #c20e26;
    }
    svg {
        width: 1.1em;
        height: 1.1em;
        flex-shrink: 0;
    }
    [data-platform='tiktok'] svg {
        filter: drop-shadow(-1px -1px 0 #25f4ee) drop-shadow(1px 1px 0 #fe2c55);
    }
</style>
