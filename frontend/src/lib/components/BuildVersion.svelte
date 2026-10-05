<script lang="ts">
    import { version as appVersion } from '../../../package.json';
</script>

<p class="build-version" title={`프론트엔드 버전 ${appVersion}`}>v{appVersion}</p>

<style>
    .build-version {
        margin: 0;
        font-size: clamp(10px, 1.2vw, 14px);
        line-height: 1.4;
        font-variant-numeric: tabular-nums;
        color: var(--m3c-on-surface-variant);
    }
</style>
