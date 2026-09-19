<script lang="ts">
    import { updated } from '$app/state';
    import '../app.css';
    let { children } = $props();

    $effect(() => {
        if (updated.current) window.location.reload();
    });
</script>

{@render children()}
