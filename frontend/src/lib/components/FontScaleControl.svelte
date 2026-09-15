<script lang="ts">
  import { onMount } from 'svelte';
  import ToolbarButton from './ToolbarButton.svelte';

  let { value = $bindable(100) }: { value?: number } = $props();
  const storageKey = 'monitor-font-scale';

  onMount(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored === null) return;
      const scale = Number(stored);
      value = scale >= 20 && scale <= 200 && scale % 5 === 0 ? scale : 100;
    } catch { /* Keep the current scale when storage is unavailable. */ }
  });

  function adjust(step: number) {
    value = Math.max(20, Math.min(200, value + step));
    try { localStorage.setItem(storageKey, String(value)); }
    catch { /* The current scale still works when storage is unavailable. */ }
  }
</script>

<div class="font-scale-control" role="group" aria-label="댓글 글자 크기">
  <ToolbarButton label="댓글 글자 작게" disabled={value <= 20} onclick={() => adjust(-5)}>
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <path d="M5 12h14" />
    </svg>
  </ToolbarButton>
  <output aria-live="polite" aria-atomic="true"><span class="sr-only">댓글 글자 크기 </span>{value}%</output>
  <ToolbarButton label="댓글 글자 크게" disabled={value >= 200} onclick={() => adjust(5)}>
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <path d="M5 12h14M12 5v14" />
    </svg>
  </ToolbarButton>
</div>

<style>
  .font-scale-control { display: flex; align-items: center; gap: 4px; }
  output { min-width: 4ch; text-align: center; font-size: .8rem; font-variant-numeric: tabular-nums; color: var(--m3c-on-surface-variant); }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
</style>
