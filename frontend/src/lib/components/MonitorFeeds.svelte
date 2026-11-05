<script lang="ts">
    import type {
        BackendState,
        FeedLayout,
        FeedMessage,
        Platform,
        StatusMessage,
    } from '$lib/types';
    import { monitorView } from '$lib/monitor-state';
    import CommentList from './CommentList.svelte';
    import LiveSummary from './LiveSummary.svelte';
    import PlatformBadge from './PlatformBadge.svelte';

    let {
        source,
        backend,
        comments,
        fontScale,
        layout,
    }: {
        source: StatusMessage;
        backend: BackendState;
        comments: FeedMessage[];
        fontScale: number;
        layout: FeedLayout;
    } = $props();
    let tiktok = $derived(comments.filter((item) => item.platform === 'tiktok'));
    let youtube = $derived(comments.filter((item) => item.platform === 'youtube'));
    let combined = $derived(comments.slice(-source.comment_history_size));
    let tiktokView = $derived(monitorView(backend, source));
    let youtubeView = $derived(monitorView(backend, source.youtube ?? null));
    let sideBySide = $derived(layout === 'side-by-side');
    const paneId = $props.id();
    const dividerSize = 12;
    let container: HTMLDivElement;
    let width = $state(0);
    let height = $state(0);
    let splitPercent = $state(50);
    let minimum = $derived(
        Math.min(
            50,
            Math.max(
                20,
                Math.ceil(
                    ((sideBySide ? 140 : 240) /
                        Math.max(1, (sideBySide ? width : height) - dividerSize)) *
                        100,
                ),
            ),
        ),
    );
    let maximum = $derived(100 - minimum);
    let share = $derived(Math.max(minimum, Math.min(maximum, splitPercent)));
    let dragStart = 0;
    let dragStartPercent = 50;
    let dragSize = 1;

    function setSplit(percent: number) {
        splitPercent = Math.max(minimum, Math.min(maximum, percent));
    }

    function startResize(event: PointerEvent) {
        if (!event.isPrimary || event.button !== 0) return;
        const handle = event.currentTarget as HTMLElement;
        dragStart = sideBySide ? event.clientX : event.clientY;
        dragStartPercent = share;
        dragSize = Math.max(
            1,
            (sideBySide ? container.clientWidth : container.clientHeight) - dividerSize,
        );
        handle.focus({ preventScroll: true });
        handle.setPointerCapture(event.pointerId);
        event.preventDefault();
    }

    function resize(event: PointerEvent) {
        const handle = event.currentTarget as HTMLElement;
        if (handle.hasPointerCapture(event.pointerId)) {
            const position = sideBySide ? event.clientX : event.clientY;
            setSplit(dragStartPercent + ((position - dragStart) / dragSize) * 100);
        }
    }

    function finishResize(event: PointerEvent) {
        const handle = event.currentTarget as HTMLElement;
        if (handle.hasPointerCapture(event.pointerId))
            handle.releasePointerCapture(event.pointerId);
    }

    function resizeWithKeyboard(event: KeyboardEvent) {
        if (event.altKey || event.ctrlKey || event.metaKey) return;
        const percent = {
            [sideBySide ? 'ArrowLeft' : 'ArrowUp']: share - 5,
            [sideBySide ? 'ArrowRight' : 'ArrowDown']: share + 5,
            Home: minimum,
            End: maximum,
        }[event.key];
        if (percent === undefined) return;
        event.preventDefault();
        setSplit(percent);
    }
</script>

{#snippet panel(platform: Platform)}
    {@const isTikTok = platform === 'tiktok'}
    {@const name = isTikTok ? 'TikTok' : 'YouTube'}
    {@const view = isTikTok ? tiktokView : youtubeView}
    {@const feed = isTikTok ? tiktok : youtube}
    <section
        class="feed-pane"
        id={`${paneId}-${platform}`}
        data-platform={platform}
        aria-label={`${name} 댓글 영역`}
    >
        <div class="pane-header">
            <h2><PlatformBadge {platform} /></h2>
            <p role="status" data-tone={view.tone}>
                {!isTikTok && !source.youtube
                    ? '연결하지 않음'
                    : view.kind === 'error'
                      ? view.description
                      : view.label}
            </p>
        </div>
        <LiveSummary {source} {backend} {platform} />
        {#if feed.length}
            <CommentList
                comments={feed}
                {fontScale}
                widthShare={sideBySide ? (isTikTok ? share : 100 - share) : 100}
                label={`${name} 실시간 댓글과 활동`}
            />
        {:else}
            <div class="empty" data-state={view.kind} role="status">
                <h3>
                    {!isTikTok && !source.youtube ? 'YouTube 방송을 연결해주세요.' : view.title}
                </h3>
                <p>
                    {!isTikTok && !source.youtube
                        ? '모니터 종료 후 첫 화면에서 방송 주소를 추가할 수 있습니다.'
                        : view.description}
                </p>
            </div>
        {/if}
    </section>
{/snippet}

<div class="monitor-feeds">
    <div
        class="feed-layout"
        class:split={layout === 'split'}
        class:columns={sideBySide}
        data-layout={layout}
        bind:this={container}
        bind:clientWidth={width}
        bind:clientHeight={height}
        style:--tiktok-share={`${share}fr`}
        style:--youtube-share={`${100 - share}fr`}
        style:--divider-size={`${dividerSize}px`}
    >
        {#key layout}
            {#if layout === 'combined'}
                <section class="feed-pane" aria-label="통합 댓글 영역">
                    <div class="combined-status">
                        <div class="combined-source">
                            <p role="status" data-tone={tiktokView.tone}>
                                <PlatformBadge platform="tiktok" />
                                <span
                                    >{tiktokView.kind === 'error'
                                        ? tiktokView.description
                                        : tiktokView.label}</span
                                >
                            </p>
                            <LiveSummary {source} {backend} />
                        </div>
                        {#if source.youtube}
                            <div class="combined-source">
                                <p role="status" data-tone={youtubeView.tone}>
                                    <PlatformBadge platform="youtube" />
                                    <span
                                        >{youtubeView.kind === 'error'
                                            ? youtubeView.description
                                            : youtubeView.label}</span
                                    >
                                </p>
                                <LiveSummary {source} {backend} platform="youtube" />
                            </div>
                        {/if}
                    </div>
                    {#if combined.length}
                        <CommentList
                            comments={combined}
                            {fontScale}
                            label="통합 실시간 댓글과 활동"
                            showPlatform
                        />
                    {:else}
                        <div class="empty" role="status">
                            <h3>댓글을 기다리고 있어요.</h3>
                            <p>연결된 방송의 댓글과 활동이 수신 순서대로 표시됩니다.</p>
                        </div>
                    {/if}
                </section>
            {:else}
                {#if layout !== 'youtube'}{@render panel('tiktok')}{/if}
                {#if layout === 'split' || sideBySide}
                    <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions (The adjustable separator supports pointer and keyboard resizing with ARIA values.) -->
                    <div
                        class="feed-divider"
                        role="separator"
                        tabindex="0"
                        aria-label="TikTok·YouTube 영역 크기 조절"
                        aria-orientation={sideBySide ? 'vertical' : 'horizontal'}
                        aria-controls={`${paneId}-tiktok ${paneId}-youtube`}
                        aria-valuemin={minimum}
                        aria-valuemax={maximum}
                        aria-valuenow={Math.round(share)}
                        aria-valuetext={`TikTok ${Math.round(share)}%, YouTube ${Math.round(100 - share)}%`}
                        title={`드래그 또는 ${sideBySide ? '←→' : '↑↓'}로 영역 크기 조절 · 두 번 클릭하면 반반`}
                        onpointerdown={startResize}
                        onpointermove={resize}
                        onpointerup={finishResize}
                        onpointercancel={finishResize}
                        onkeydown={resizeWithKeyboard}
                        ondblclick={() => setSplit(50)}
                    ></div>
                {/if}
                {#if layout !== 'tiktok'}{@render panel('youtube')}{/if}
            {/if}
        {/key}
    </div>
</div>

<style>
    .monitor-feeds,
    .feed-pane {
        display: flex;
        flex-direction: column;
        flex: 1;
        min-height: 0;
        min-width: 0;
        gap: 8px;
    }
    .feed-layout {
        display: grid;
        flex: 1;
        min-height: 0;
        min-width: 0;
        grid-template-rows: minmax(0, 1fr);
    }
    .feed-layout.split {
        grid-template-rows:
            minmax(0, var(--tiktok-share)) var(--divider-size)
            minmax(0, var(--youtube-share));
    }
    .feed-layout.columns {
        grid-template-columns:
            minmax(0, var(--tiktok-share)) var(--divider-size)
            minmax(0, var(--youtube-share));
    }
    .feed-pane {
        overflow: hidden;
    }
    .feed-divider {
        position: relative;
        z-index: 1;
        align-self: center;
        height: 44px;
        cursor: row-resize;
        touch-action: none;
        user-select: none;
        border-radius: 4px;
    }
    .feed-divider::before {
        content: '';
        position: absolute;
        top: calc(50% - 2px);
        left: calc(50% - 32px);
        width: 64px;
        height: 4px;
        border-radius: 2px;
        background: var(--m3c-outline);
    }
    .feed-divider:hover::before,
    .feed-divider:focus-visible::before {
        background: var(--m3c-on-surface);
    }
    .feed-divider:focus-visible {
        outline: 2px solid var(--m3c-secondary);
        outline-offset: -2px;
    }
    .columns .feed-divider {
        align-self: stretch;
        justify-self: center;
        width: 44px;
        height: auto;
        cursor: col-resize;
    }
    .columns .feed-divider::before {
        top: calc(50% - 32px);
        left: calc(50% - 2px);
        width: 4px;
        height: 64px;
    }
    .feed-pane[data-platform] {
        --platform-accent: var(--platform-tiktok);
        padding: clamp(8px, 1.2vw, 12px);
        border: 1px solid color-mix(in srgb, var(--platform-accent) 50%, var(--m3c-surface));
        border-top: 4px solid var(--platform-accent);
        border-radius: 12px;
        background: color-mix(in srgb, var(--platform-accent) 7%, var(--m3c-surface));
    }
    .feed-pane[data-platform='youtube'] {
        --platform-accent: var(--platform-youtube);
    }
    .pane-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 4px 12px;
        flex-shrink: 0;
    }
    .pane-header {
        padding-bottom: 6px;
        border-bottom: 1px solid color-mix(in srgb, var(--platform-accent) 25%, transparent);
    }
    h2 {
        margin: 0;
        font-size: clamp(16px, 2vw, 20px);
    }
    .pane-header p,
    .combined-status p {
        margin: 0;
        font-size: 0.7rem;
        color: var(--m3c-on-surface-variant);
        overflow-wrap: anywhere;
    }
    .combined-status p {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
    }
    p[data-tone='error'] {
        color: var(--m3c-error);
    }
    p[data-tone='waiting'] {
        color: var(--monitor-waiting);
    }
    .combined-status {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
        gap: 8px 16px;
        flex-shrink: 0;
    }
    .combined-source {
        display: flex;
        flex-direction: column;
        gap: 6px;
        min-width: 0;
    }
    .empty {
        display: flex;
        flex: 1;
        flex-direction: column;
        justify-content: safe center;
        min-height: 0;
        overflow: auto;
    }
    .empty h3 {
        margin: 12px 0;
        font-size: clamp(24px, 4vw, 44px);
        line-height: 1.35;
    }
    .empty p {
        margin: 0;
        font-size: 0.8rem;
        line-height: 1.6;
        color: var(--m3c-on-surface-variant);
    }
</style>
