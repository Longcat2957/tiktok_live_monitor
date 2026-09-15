<script lang="ts">
  import type { BackendState } from '../types';
  let { backend }: { backend: BackendState } = $props();
  let message = $derived(backend === 'connected' ? '서버 연결됨' :
    backend === 'connecting' ? '서버 연결중' : '서버 연결실패');
</script>

<div class="connection" role="status" data-state={backend}>
  <span class="status-dot" aria-hidden="true"></span>
  <span>{message}</span>
</div>
