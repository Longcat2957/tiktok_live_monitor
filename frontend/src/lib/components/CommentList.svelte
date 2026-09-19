<script lang="ts">
    import { onDestroy, onMount, tick, untrack } from 'svelte';
    import { Button } from 'm3-svelte';
    import type { FeedMessage } from '../types';
    import CommentItem from './CommentItem.svelte';
    let { comments, fontScale }: { comments: FeedMessage[]; fontScale: number } = $props();
    let viewport: HTMLDivElement;
    let following = $state(true);
    let unread = $state(0);
    let anchorLost = $state(false);
    let announcement = $state('');
    let lastId: string | undefined;
    let lastScrollTop = 0;
    let revision = 0;
    let pendingAnnouncement = 0;
    let announcementTimer: ReturnType<typeof setTimeout> | undefined;

    function moveTo(top: number) {
        viewport.scrollTop = top;
        lastScrollTop = viewport.scrollTop;
    }

    function onScroll() {
        if (!viewport?.isConnected) return;
        // Ignore our own anchor corrections; only a changed position changes reading mode.
        if (Math.abs(viewport.scrollTop - lastScrollTop) < 1) return;
        lastScrollTop = viewport.scrollTop;
        following = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop <= 2;
        if (following) {
            unread = 0;
            anchorLost = false;
        }
    }

    async function goLatest() {
        following = true;
        unread = 0;
        anchorLost = false;
        await tick();
        if (viewport?.isConnected) {
            moveTo(viewport.scrollHeight);
            viewport.focus({ preventScroll: true });
        }
    }

    function onKeydown(event: KeyboardEvent) {
        if (event.altKey || event.metaKey || event.ctrlKey) return;
        if (event.key === 'End') {
            event.preventDefault();
            void goLatest();
            return;
        }
        const distance = {
            ArrowUp: -40,
            ArrowDown: 40,
            PageUp: -viewport.clientHeight * 0.9,
            PageDown: viewport.clientHeight * 0.9,
            Home: -viewport.scrollHeight,
        }[event.key];
        if (distance === undefined) return;
        event.preventDefault();
        if (
            distance > 0 &&
            viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop <= 2
        ) {
            void goLatest();
            return;
        }
        // Apply keyboard movement immediately so incoming rows cannot interrupt its animation.
        following = false;
        viewport.scrollTop += distance;
        onScroll();
    }

    $effect.pre(() => {
        void fontScale; // Track scale changes before measuring the reading anchor.
        const current = comments;
        const added =
            current.length - (lastId ? current.findIndex((item) => item.id === lastId) + 1 : 0);
        lastId = current.at(-1)?.id;
        const update = ++revision;
        const anchor = untrack(() => {
            if (following || !viewport) return null;
            const top = viewport.getBoundingClientRect().top;
            const first = [...viewport.querySelectorAll<HTMLElement>('[data-comment-id]')].find(
                (item) => item.getBoundingClientRect().bottom > top + 1,
            );
            return first
                ? { id: first.dataset.commentId, offset: first.getBoundingClientRect().top - top }
                : null;
        });
        untrack(() => {
            unread = following ? 0 : Math.min(current.length, unread + added);
            if (added > 0) {
                pendingAnnouncement = Math.min(current.length, pendingAnnouncement + added);
                if (!announcementTimer) {
                    announcement = '';
                    announcementTimer = setTimeout(() => {
                        announcement = `새 댓글과 활동 ${pendingAnnouncement}개가 도착했습니다.`;
                        pendingAnnouncement = 0;
                        announcementTimer = undefined;
                    }, 1000);
                }
            }
        });
        void tick().then(() => {
            if (update !== revision || !viewport?.isConnected) return;
            if (following) moveTo(viewport.scrollHeight);
            else if (anchor) {
                const item = [...viewport.querySelectorAll<HTMLElement>('[data-comment-id]')].find(
                    (item) => item.dataset.commentId === anchor.id,
                );
                if (item)
                    moveTo(
                        viewport.scrollTop +
                            item.getBoundingClientRect().top -
                            viewport.getBoundingClientRect().top -
                            anchor.offset,
                    );
                else {
                    moveTo(0);
                    anchorLost = true;
                }
            }
        });
    });

    onMount(() => {
        const observer = new ResizeObserver(() => {
            if (following) moveTo(viewport.scrollHeight);
        });
        observer.observe(viewport);
        return () => observer.disconnect();
    });

    onDestroy(() => {
        revision++;
        clearTimeout(announcementTimer);
    });
</script>

<div class="feed" style:--comment-scale={fontScale / 100}>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions (The scroll region supports focused keyboard navigation.) -->
    <div
        class="comment-viewport"
        bind:this={viewport}
        onscroll={onScroll}
        onkeydown={onKeydown}
        onwheel={(event) => {
            if (!event.ctrlKey && !event.metaKey && event.deltaY < 0) following = false;
        }}
        tabindex="0"
        role="region"
        aria-label="실시간 댓글과 활동"
        aria-describedby="feed-help"
    >
        <div class="comment-list">
            {#each comments as comment (comment.id)}
                <CommentItem {comment} />
            {/each}
        </div>
    </div>
    {#if !following}
        <div class="reading-controls">
            <p>
                {anchorLost ? '읽던 항목이 보관 범위를 벗어났습니다.' : '이전 댓글을 읽는 중'}
                {#if unread > 0}<span>보관 중인 새 항목 {unread}개</span>{/if}
            </p>
            <Button type="button" variant="tonal" size="s" onclick={goLatest}>최신 댓글로</Button>
        </div>
    {/if}
    <p id="feed-help" class="sr-only">
        위로 스크롤하면 최신 댓글로 자동 이동하지 않습니다. 방향키와 Page Up, Page Down으로 읽고 End
        키로 최신 댓글로 이동하세요.
    </p>
    <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
</div>

<style>
    .comment-viewport {
        flex: 1;
        min-height: 0;
        overflow: auto;
        scrollbar-width: none;
        overflow-anchor: none;
    }
    .comment-viewport::-webkit-scrollbar {
        display: none;
    }
    .comment-list {
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
        min-height: 100%;
    }
    .feed {
        flex: 1;
        min-height: 0;
        display: flex;
        flex-direction: column;
    }
    .comment-viewport:focus-visible {
        outline: 2px solid var(--m3c-secondary);
        outline-offset: -2px;
        border-radius: 4px;
    }
    .reading-controls {
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding-top: 8px;
    }
    .reading-controls p {
        margin: 0;
        color: var(--m3c-on-surface-variant);
        font-size: 0.7rem;
        line-height: 1.5;
    }
    .reading-controls p span {
        display: block;
    }
    .reading-controls :global(button) {
        flex-shrink: 0;
    }
    .sr-only {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border: 0;
    }
</style>
