<script lang="ts">
    import { untrack } from 'svelte';
    import { Button, ConnectedButtons, TextFieldOutlined } from 'm3-svelte';
    import type { BackendState, Source, StatusMessage } from '$lib/types';

    let {
        source,
        blocked,
        saving,
        backend,
        onstart,
    }: {
        source: StatusMessage;
        blocked: boolean;
        saving: boolean;
        backend: BackendState;
        onstart: (mode: Source, account: string) => Promise<string | null>;
    } = $props();
    let sessionId = untrack(() => source.session_id);
    let mode = $state<Source>(untrack(() => source.source));
    let account = $state(untrack(() => source.username ?? ''));
    let error = $state('');
    let panel: HTMLElement;

    $effect(() => {
        if (sessionId !== source.session_id) {
            sessionId = source.session_id;
            mode = source.source;
            account = source.username ?? '';
            error = '';
        }
    });

    export function focus() {
        const target =
            panel?.querySelector<HTMLElement>('.account-field input:not(:disabled)') ??
            panel?.querySelector<HTMLElement>('input[type="radio"]:checked');
        target?.focus({ preventScroll: true });
    }

    async function submit(event: SubmitEvent) {
        event.preventDefault();
        if (blocked) return;
        const expected = source.session_id;
        error = '';
        try {
            const problem = await onstart(mode, account);
            if (source.session_id === expected) error = problem ?? '';
        } catch {
            if (source.session_id === expected)
                error = '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.';
        }
    }
</script>

<section class="account-panel" aria-labelledby="setup-title" bind:this={panel}>
    <div class="setup-intro">
        <span class="eyebrow">READY WHEN YOU ARE</span>
        <h1 id="setup-title">지금, 시청자의<br /><span>이야기를 만나세요.</span></h1>
        <p>방송을 연결하거나 데모로 먼저 둘러보세요.</p>
    </div>
    <form onsubmit={submit}>
        <fieldset disabled={blocked}>
            <legend>방송 또는 데모</legend>
            <ConnectedButtons>
                <Button variant="tonal" size="m" square label>
                    <input
                        type="radio"
                        name="mode"
                        value="tiktok"
                        bind:group={mode}
                        onchange={() => (error = '')}
                    />실제 방송
                </Button>
                <Button variant="tonal" size="m" square label>
                    <input
                        type="radio"
                        name="mode"
                        value="mock"
                        bind:group={mode}
                        onchange={() => (error = '')}
                    />데모 체험
                </Button>
            </ConnectedButtons>
        </fieldset>
        <div class="mode-details">
            <div class="mode-content" aria-hidden={mode !== 'tiktok'} inert={mode !== 'tiktok'}>
                <div class="account-field">
                    <TextFieldOutlined
                        label="TikTok 아이디 또는 방송 주소"
                        bind:value={account}
                        required={mode === 'tiktok'}
                        maxlength={256}
                        autocomplete="off"
                        autocapitalize="none"
                        spellcheck="false"
                        disabled={blocked || mode !== 'tiktok'}
                        error={Boolean(error)}
                        aria-invalid={Boolean(error)}
                        aria-describedby={error ? 'account-hint account-error' : 'account-hint'}
                    />
                </div>
                <p id="account-hint">
                    @아이디 또는 TikTok 프로필·LIVE 주소를 입력하세요.<br />방송 전이라면 시작할
                    때까지 기다립니다.
                </p>
            </div>
            <div class="mode-content" aria-hidden={mode !== 'mock'} inert={mode !== 'mock'}>
                <div class="demo-description">
                    <span class="demo-badge">DEMO</span>
                    <h2>방송 없이, 바로 체험.</h2>
                </div>
                <p>
                    가상의 댓글·선물·통계와 방송 상태를 확인하세요.<br />계정 입력이나 실제 방송
                    연결은 필요하지 않습니다.
                </p>
            </div>
        </div>
        {#if error}<p id="account-error" role="alert">{error}</p>{/if}
        <div class="account-actions">
            <Button type="submit" size="m" square disabled={blocked || backend !== 'connected'}
                >{saving ? '시작 준비 중…' : '시작'}</Button
            >
        </div>
        <p class="session-note">장비를 다시 켜면 모드를 선택하고 다시 시작해주세요.</p>
    </form>
</section>

<style>
    .account-panel {
        flex: 1;
        min-height: 0;
        overflow: auto;
        display: flex;
        flex-direction: column;
        justify-content: safe center;
        gap: 36px;
        max-width: 840px;
        width: 100%;
        margin-inline: auto;
        padding: 24px 4px;
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
    h1 span {
        color: var(--m3c-on-surface-variant);
    }
    .setup-intro p {
        margin: 0;
        font-size: 1rem;
        color: var(--m3c-on-surface-variant);
        line-height: 1.6;
    }
    form {
        display: flex;
        flex-direction: column;
        gap: 24px;
        padding: clamp(20px, 3vw, 36px);
        border: 1px solid var(--m3c-outline-variant);
        border-radius: 24px;
        background: var(--m3c-surface-container-low);
    }
    fieldset {
        border: 0;
        padding: 0;
        margin: 0;
        min-width: 0;
    }
    legend {
        margin-bottom: 12px;
        padding: 0;
        font-size: 0.85rem;
        font-weight: 700;
    }
    /* Both modes size the same grid cell; switching visibility never moves the form. */
    .mode-details {
        display: grid;
        min-height: 120px;
    }
    .mode-content {
        grid-area: 1 / 1;
        display: flex;
        flex-direction: column;
        gap: 16px;
        min-width: 0;
    }
    .mode-content[aria-hidden='true'] {
        visibility: hidden;
    }
    .account-field {
        display: flex;
        flex-direction: column;
        min-width: 0;
    }
    .account-field > :global(div) {
        min-width: 0;
    }
    form p {
        margin: 0;
        font-size: 0.8rem;
        line-height: 1.7;
        color: var(--m3c-on-surface-variant);
    }
    .demo-description {
        display: flex;
        gap: 12px;
        align-items: center;
    }
    .demo-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 5px;
        padding: 5px 9px;
        font-size: 0.7rem;
        font-weight: 850;
        letter-spacing: 0.08em;
        background: var(--m3c-secondary-container);
        color: var(--m3c-on-secondary-container);
    }
    h2 {
        font-size: 1.1rem;
        margin: 0;
        font-weight: 700;
    }
    .account-actions {
        display: flex;
        gap: 12px;
    }
    .account-actions > :global(button:first-child) {
        flex: 1;
    }
    form [role='alert'] {
        color: var(--m3c-error);
    }
    form .session-note {
        font-size: 0.7rem;
    }
    @media (width < 480px) {
        .account-panel {
            gap: 24px;
        }
        .demo-description {
            flex-wrap: wrap;
        }
    }
</style>
