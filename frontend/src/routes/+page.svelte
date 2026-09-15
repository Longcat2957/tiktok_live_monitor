<script lang="ts">
  import { onMount } from 'svelte';
  import CommentList from '$lib/components/CommentList.svelte';
  import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
  import { DEFAULT_HISTORY_SIZE } from '$lib/config';
  import { appendComment } from '$lib/history';
  import { connectMonitor, websocketUrl } from '$lib/websocket';
  import type { BackendState, CommentMessage, StatusMessage } from '$lib/types';

  let comments = $state<CommentMessage[]>([]);
  let backend = $state<BackendState>('connecting');
  let source = $state<StatusMessage | null>(null);
  let limit = DEFAULT_HISTORY_SIZE;
  onMount(() => {
    const controller = new AbortController();
    const disconnect = connectMonitor(websocketUrl(window.location), (message) => {
      if (message.type === 'comment') comments = appendComment(comments, message, limit);
      else source = message;
    }, (state) => {
      backend = state;
      if (state !== 'connected') source = null;
      if (state === 'connected') {
        void fetch('/config', { signal: controller.signal }).then((response) => response.json()).then((config) => {
          if (Number.isInteger(config.comment_history_size) && config.comment_history_size > 0 && config.comment_history_size <= 1000) {
            limit = config.comment_history_size;
            comments = comments.slice(-limit);
          }
        }).catch(() => { /* Default history limit remains bounded while offline. */ });
      }
    });
    return () => { controller.abort(); disconnect(); };
  });
</script>

<svelte:head><title>TikTok LIVE · 댓글 모니터</title><meta name="description" content="실시간 LIVE 댓글 모니터" /></svelte:head>

<main>
  <header><span class="wordmark">LIVE <span>COMMENTS</span></span><span class="portrait-mark" aria-hidden="true">●</span></header>
  {#if comments.length === 0}
    <section class="empty"><span class="empty-label">댓글 모니터</span><h1>시청자의 이야기를<br />기다리고 있어요.</h1><p>방송에 연결되면 댓글이 여기에 표시됩니다.</p></section>
  {/if}
  <CommentList {comments} />
  <footer><ConnectionStatus {backend} {source} /></footer>
</main>
