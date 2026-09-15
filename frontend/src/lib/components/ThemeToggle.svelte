<script lang="ts">
  import { onMount } from 'svelte';
  import ToolbarButton from './ToolbarButton.svelte';
  let light = $state(false);
  onMount(() => { light = document.documentElement.dataset.theme === 'light'; });
  function toggleTheme() {
    light = !light;
    const theme = light ? 'light' : 'dark';
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', light ? '#ffffff' : '#000000');
    try { localStorage.setItem('monitor-theme', theme); } catch { /* The current theme still works when storage is unavailable. */ }
  }
</script>

<ToolbarButton label={light ? '다크 테마로 전환' : '라이트 테마로 전환'} onclick={toggleTheme}>
  <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    {#if light}
      <path d="M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13Z" />
    {:else}
      <circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" />
    {/if}
  </svg>
</ToolbarButton>
