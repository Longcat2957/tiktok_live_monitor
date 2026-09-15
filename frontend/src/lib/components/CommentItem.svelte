<script lang="ts">
  import type { CommentMessage } from '../types';
  let { comment }: { comment: CommentMessage } = $props();
</script>

<article class="comment" data-comment-id={comment.id}>
  <p class="nickname">{comment.user.nickname || comment.user.unique_id || '시청자'}</p>
  <p class="body">{comment.comment}</p>
</article>
