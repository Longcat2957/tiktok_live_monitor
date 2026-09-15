<script lang="ts">
  import type { BackendState, StatusMessage } from '../types';
  let { backend, source }: { backend: BackendState; source: StatusMessage | null } = $props();
  let state = $derived(backend === 'connected' ? source?.state ?? 'connecting' : backend);
  let message = $derived(backend === 'connected' ? source?.message ?? '방송 상태 확인 중' :
    backend === 'connecting' ? '서버 연결 중' : '서버 연결 끊김 · 자동 재연결 중');
</script>

<div class="connection" role="status" data-state={state}>
  <span class="status-dot" aria-hidden="true"></span>
  <span>{message}</span>
  {#if backend === 'connected'}<span class="server-label">서버 연결됨</span>{/if}
</div>
