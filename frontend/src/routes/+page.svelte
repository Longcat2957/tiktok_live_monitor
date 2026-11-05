<script lang="ts">
    import { onMount, tick } from 'svelte';
    import AccountSetup from '$lib/components/AccountSetup.svelte';
    import BuildVersion from '$lib/components/BuildVersion.svelte';
    import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
    import MonitorFeeds from '$lib/components/MonitorFeeds.svelte';
    import MonitorHeader from '$lib/components/MonitorHeader.svelte';
    import RequestFeedback from '$lib/components/RequestFeedback.svelte';
    import SettingsDialog from '$lib/components/SettingsDialog.svelte';
    import { MonitorCommands } from '$lib/monitor/commands.svelte.js';
    import { MonitorSession } from '$lib/monitor/session.svelte.js';
    import { monitorView } from '$lib/monitor-state';
    import type { FeedLayout } from '$lib/types';

    const session = new MonitorSession();
    const commands = new MonitorCommands(() => session.source);
    let fontScale = $state(100);
    let layout = $state<FeedLayout>('split');
    let layoutSession: string | undefined;
    let editing = $state(false);
    let header = $state<{ focus(): void }>();
    let setupPanel = $state<{ focus(): void }>();
    let showSetup = $derived(session.source?.state === 'idle');
    let view = $derived(monitorView(session.backend, session.source));
    let previousSetup: boolean | undefined;

    $effect(() => {
        if (session.source && session.source.session_id !== layoutSession) {
            layoutSession = session.source.session_id;
            layout = session.source.youtube ? 'split' : 'tiktok';
        }
    });

    $effect(() => {
        if (!session.source || commands.blocked || editing) return;
        const setup = showSetup;
        const changed = previousSetup !== undefined && previousSetup !== setup;
        previousSetup = setup;
        if (changed)
            void tick().then(() => {
                if (setup === showSetup && !commands.blocked && !editing)
                    (setup ? setupPanel : header)?.focus();
            });
    });

    async function updateMonitor(action: 'refresh' | 'stop') {
        if ((await commands[action]()) === null) editing = false;
    }

    onMount(() => {
        const disconnect = session.connect((status) => commands.acceptStatus(status));
        return () => {
            commands.dispose();
            disconnect();
        };
    });
</script>

<svelte:head
    ><title>LIVE · 댓글 모니터</title><meta
        name="description"
        content="실시간 LIVE 댓글 모니터"
    /></svelte:head
>

<main>
    <MonitorHeader
        bind:this={header}
        active={Boolean(session.source && !showSetup)}
        blocked={commands.blocked}
        bind:fontScale
        bind:layout
        onsettings={() => (editing = true)}
        onrefresh={() => void updateMonitor('refresh')}
        onstop={() => void updateMonitor('stop')}
    />
    <RequestFeedback
        actionError={commands.actionError}
        source={session.source}
        recoveryMessage={commands.recoveryMessage}
        pending={commands.pendingSession !== null}
        checking={commands.checking}
        oncheck={() => void commands.checkResult()}
    />
    {#if showSetup && session.source}
        <AccountSetup
            bind:this={setupPanel}
            source={session.source}
            blocked={commands.blocked}
            saving={commands.saving}
            backend={session.backend}
            onstart={(mode, account, youtubeVideo) => commands.start(mode, account, youtubeVideo)}
        />
    {:else if session.source}
        {#key session.source.session_id}
            <MonitorFeeds
                source={session.source}
                backend={session.backend}
                comments={session.comments}
                {fontScale}
                {layout}
            />
        {/key}
    {:else}
        <section class="empty" data-state={view.kind} role="status">
            <span class="eyebrow">LIVE MONITOR</span>
            <h1>{view.title}</h1>
            <p>{view.description}</p>
        </section>
    {/if}
    <footer>
        <div class="footer-info">
            <BuildVersion />
        </div>
        <ConnectionStatus backend={session.backend} />
    </footer>
</main>

{#if editing && session.source}
    <SettingsDialog
        source={session.source}
        blocked={commands.blocked}
        recoveryMessage={commands.recoveryMessage}
        onapply={(settings, expected) => commands.updateSettings(settings, expected)}
        onclose={() => (editing = false)}
    />
{/if}

<style>
    main {
        height: 100dvh;
        display: flex;
        flex-direction: column;
        padding: clamp(12px, 2vw, 24px);
        gap: 10px;
    }
    .empty {
        flex: 1;
        min-height: 0;
        overflow: auto;
        display: flex;
        flex-direction: column;
        justify-content: safe center;
    }
    .eyebrow {
        color: var(--m3c-secondary);
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.15em;
    }
    h1 {
        margin: 20px 0;
        font-size: clamp(32px, 5.5vw, 64px);
        font-weight: 800;
        line-height: 1.25;
        letter-spacing: -0.045em;
    }
    .empty p {
        margin: 0;
        font-size: 1rem;
        color: var(--m3c-on-surface-variant);
        line-height: 1.6;
    }
    footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        flex-shrink: 0;
        border-top: 1px solid var(--m3c-outline-variant);
        padding-top: 8px;
    }
    .footer-info {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 4px;
    }
</style>
