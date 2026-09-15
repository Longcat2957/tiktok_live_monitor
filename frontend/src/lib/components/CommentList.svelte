<script lang="ts">
  import { tick } from 'svelte';
  import type { CommentMessage } from '../types';
  import CommentItem from './CommentItem.svelte';
  let { comments }: { comments: CommentMessage[] } = $props();
  let viewport: HTMLDivElement;
  $effect(() => {
    comments.length;
    comments.at(-1)?.id;
    void tick().then(() => { if (viewport) viewport.scrollTop = viewport.scrollHeight; });
  });
</script>

<div class="comment-viewport" bind:this={viewport}>
  <div class="comment-list" role="log" aria-label="실시간 댓글" aria-live="polite" aria-relevant="additions">
    {#each comments as comment (comment.id)}
      <CommentItem {comment} />
    {/each}
  </div>
</div>
