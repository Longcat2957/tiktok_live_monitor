<script lang="ts">
  import { safeAvatar, type FeedMessage } from '../types';
  let { comment }: { comment: FeedMessage } = $props();
  let imageFailed = $state(false);
  let name = $derived(comment.user.nickname || comment.user.unique_id || '시청자');
  const labels = { gift: '선물', follow: '팔로우', share: '공유', subscribe: '구독' };
  let activityText = $derived(comment.type === 'activity' ?
    comment.kind === 'gift' ? `${comment.gift_name} × ${comment.count.toLocaleString('ko-KR')}` :
    comment.kind === 'follow' ? '방송을 팔로우했어요' :
    comment.kind === 'share' ? '방송을 공유했어요' : '구독을 알렸어요' : '');
</script>

{#snippet avatar()}
  <span class="avatar" aria-hidden="true">
    {#if !imageFailed && safeAvatar(comment.user.avatar_url)}
      <img src={comment.user.avatar_url} alt="" width="40" height="40" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror={() => imageFailed = true} />
    {:else}
      <span>{Array.from(name)[0]}</span>
    {/if}
  </span>
{/snippet}

<article class="comment" class:activity={comment.type === 'activity'} data-comment-id={comment.id} data-kind={comment.type === 'activity' ? comment.kind : 'comment'}>
  {#if comment.type === 'activity'}
    {@render avatar()}
    <div class="activity-content">
      <p class="nickname" title={name}>{name}</p>
      <p class="body" title={activityText}>{activityText}</p>
    </div>
    <span class="activity-label">{labels[comment.kind]}</span>
  {:else}
    <div class="comment-author">
      {@render avatar()}
      <p class="nickname">{name}</p>
      {#each comment.user.badges ?? [] as badge}
        <span class="user-badge" data-kind={badge.kind}>{badge.kind === 'subscriber' ? '구독자' : '팬'}{badge.level == null ? '' : ` Lv.${badge.level}`}</span>
      {/each}
    </div>
    <p class="body">{comment.comment}</p>
  {/if}
</article>

<style>
  .activity {
    display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center;
    gap: 10px; padding-block: clamp(10px, 1.4vw, 18px);
  }
  .activity .avatar { width: max(20px, calc(30px * var(--comment-scale, 1))); height: max(20px, calc(30px * var(--comment-scale, 1))); }
  .activity-content { display: flex; align-items: baseline; flex-wrap: wrap; gap: 2px 10px; min-width: 0; }
  .activity .nickname {
    margin: 0; min-width: 0; max-width: 100%; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; font-size: calc(clamp(16px, 2.2vw, 24px) * var(--comment-scale, 1)); line-height: 1.4;
  }
  .activity .body {
    min-width: 0; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    font-size: calc(clamp(16px, 2.2vw, 24px) * var(--comment-scale, 1));
    line-height: 1.4; color: var(--m3c-on-secondary-container);
  }
  .activity-label { margin-left: 0; white-space: nowrap; }
</style>
