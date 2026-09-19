<script lang="ts">
    import { safeAvatar, type FeedMessage } from '../types';
    let { comment }: { comment: FeedMessage } = $props();
    let imageFailed = $state(false);
    let name = $derived(comment.user.nickname || comment.user.unique_id || '시청자');
    const labels = { gift: '선물', follow: '팔로우', share: '공유', subscribe: '구독' };
    let activityText = $derived(
        comment.type === 'activity'
            ? comment.kind === 'gift'
                ? `${comment.gift_name} × ${comment.count.toLocaleString('ko-KR')}`
                : comment.kind === 'follow'
                  ? '방송을 팔로우했어요'
                  : comment.kind === 'share'
                    ? '방송을 공유했어요'
                    : '구독을 알렸어요'
            : '',
    );
</script>

{#snippet avatar()}
    <span class="avatar" aria-hidden="true">
        {#if !imageFailed && safeAvatar(comment.user.avatar_url)}
            <img
                src={comment.user.avatar_url}
                alt=""
                width="40"
                height="40"
                loading="lazy"
                decoding="async"
                referrerpolicy="no-referrer"
                onerror={() => (imageFailed = true)}
            />
        {:else}
            <span>{Array.from(name)[0]}</span>
        {/if}
    </span>
{/snippet}

<article
    class="comment"
    class:activity={comment.type === 'activity'}
    data-comment-id={comment.id}
    data-kind={comment.type === 'activity' ? comment.kind : 'comment'}
>
    {#if comment.type === 'activity'}
        <div class="activity-header">
            {@render avatar()}
            <p class="nickname" title={name}>{name}</p>
            <span class="activity-label">{labels[comment.kind]}</span>
        </div>
        <p class="body">{activityText}</p>
    {:else}
        <div class="comment-author">
            {@render avatar()}
            <p class="nickname">{name}</p>
            {#each comment.user.badges ?? [] as badge (badge.kind)}
                <span class="user-badge" data-kind={badge.kind}
                    >{badge.kind === 'subscriber' ? '구독자' : '팬'}{badge.level == null
                        ? ''
                        : ` Lv.${badge.level}`}</span
                >
            {/each}
        </div>
        <p class="body">{comment.comment}</p>
    {/if}
</article>

<style>
    .comment {
        flex-shrink: 0;
        padding: clamp(18px, 2.7vw, 34px) 0;
        border-bottom: 1px solid var(--m3c-outline-variant);
        min-width: 0;
    }
    .comment:last-child {
        border-bottom: 0;
        padding-bottom: 8px;
    }
    .nickname {
        margin: 0 0 10px;
        font-size: calc(clamp(17px, 2.4vw, 27px) * var(--comment-scale, 1));
        color: var(--m3c-on-surface-variant);
        line-height: 1.4;
        overflow-wrap: anywhere;
    }
    .body {
        margin: 0;
        font-size: calc(clamp(28px, 4.4vw, 52px) * var(--comment-scale, 1));
        font-weight: 600;
        line-height: 1.45;
        letter-spacing: -0.025em;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        word-break: normal;
    }
    .comment-author {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 6px 10px;
        margin-bottom: 10px;
    }
    .comment-author .nickname {
        margin: 0;
    }
    .avatar {
        width: max(20px, calc(40px * var(--comment-scale, 1)));
        height: max(20px, calc(40px * var(--comment-scale, 1)));
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        border-radius: 50%;
        background: var(--m3c-surface-container-high);
        color: var(--m3c-on-surface-variant);
        font-size: max(12px, calc(18px * var(--comment-scale, 1)));
    }
    .avatar img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
    .user-badge,
    .activity-label {
        border-radius: 4px;
        padding: 2px 6px;
        font-size: max(10px, calc(12px * var(--comment-scale, 1)));
        font-weight: 700;
    }
    .user-badge {
        color: var(--m3c-on-primary-container);
        background: var(--m3c-primary-container);
    }
    .user-badge[data-kind='fan'] {
        color: var(--m3c-on-secondary-container);
        background: var(--m3c-secondary-container);
    }
    .comment.activity {
        margin-block: 8px;
        padding: clamp(18px, 2.7vw, 30px);
        border: 0;
        border-radius: 16px;
        background: color-mix(in srgb, var(--activity-accent) 24%, var(--m3c-surface));
        color: var(--m3c-on-surface);
    }
    .activity[data-kind='gift'] {
        --activity-accent: #ff4d80;
    }
    .activity[data-kind='follow'] {
        --activity-accent: #20cf9a;
    }
    .activity[data-kind='share'] {
        --activity-accent: #4c9dff;
    }
    .activity[data-kind='subscribe'] {
        --activity-accent: #bc82ff;
    }
    .activity-header {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px 12px;
        margin-bottom: 12px;
    }
    .activity .nickname {
        flex: 1;
        margin: 0;
        min-width: 0;
        font-size: calc(clamp(20px, 2.8vw, 32px) * var(--comment-scale, 1));
        color: inherit;
    }
    .activity .body {
        font-size: calc(clamp(32px, 5.2vw, 62px) * var(--comment-scale, 1));
        font-weight: 750;
        line-height: 1.3;
    }
    .activity-label {
        padding: 4px 8px;
        border: 1px solid currentColor;
        font-size: max(12px, calc(clamp(13px, 1.8vw, 20px) * var(--comment-scale, 1)));
        overflow-wrap: anywhere;
    }
</style>
