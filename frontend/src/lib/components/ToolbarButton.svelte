<script lang="ts">
  import { Button } from 'm3-svelte';
  import type { Snippet } from 'svelte';

  let { label, disabled = false, onclick, children }: {
    label: string; disabled?: boolean; onclick: () => void; children: Snippet;
  } = $props();
  let dismissed = $state(false);
  const tooltipId = $props.id();
</script>

<div class="toolbar-action">
  <Button variant="outlined" size="m" iconType="full" aria-label={label}
    aria-describedby={tooltipId} {disabled} {onclick}
    onpointerenter={() => dismissed = false} onfocus={() => dismissed = false}
    onkeydown={(event: KeyboardEvent) => { if (event.key === 'Escape') dismissed = true; }}>
    {@render children()}
  </Button>
  <span id={tooltipId} role="tooltip" class="action-tooltip" hidden={dismissed}>{label}</span>
</div>

<style>
  .toolbar-action { position: relative; }
  .action-tooltip {
    position: absolute; top: 100%; right: 0; z-index: 2; visibility: hidden;
    padding: 8px 12px; border-radius: 8px; white-space: nowrap; font-size: .75rem;
    color: var(--m3c-inverse-on-surface); background: var(--m3c-inverse-surface);
  }
  .toolbar-action:hover .action-tooltip, .toolbar-action:focus-within .action-tooltip { visibility: visible; }
</style>
