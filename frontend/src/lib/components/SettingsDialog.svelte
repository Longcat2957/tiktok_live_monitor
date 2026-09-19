<script lang="ts">
    import { onMount, untrack } from 'svelte';
    import { Button, Dialog, SelectOutlined, TextFieldOutlined } from 'm3-svelte';
    import type { StatusMessage } from '$lib/types';
    import { requestJson } from '$lib/api';

    let {
        source,
        blocked,
        recoveryMessage,
        onapply,
        onclose,
    }: {
        source: StatusMessage;
        blocked: boolean;
        recoveryMessage: string;
        onapply: (settings: Record<string, unknown>, sessionId: string) => Promise<string | null>;
        onclose: () => void;
    } = $props();
    let open = $state(true);
    // Draft values are isolated until Apply; cancelling does not change the receiver.
    const mode = untrack(() => source.source);
    const sessionId = untrack(() => source.session_id);
    const title = mode === 'tiktok' ? '실제 방송 설정' : '데모 설정';
    let values = $state<Record<string, string>>({});
    let logLevel = $state('INFO');
    let loading = $state(true);
    let saving = $state(false);
    let error = $state('');
    let advanced: HTMLDetailsElement;
    const fields = [
        {
            key: 'comment_history_size',
            label: '목록 보관 수',
            hint: '화면에 유지할 최근 댓글과 활동 알림의 합계',
            min: 1,
            max: 1000,
            step: '1',
        },
        {
            key: 'comment_queue_size',
            label: '수신 대기 큐 크기',
            hint: '화면으로 전달하기 전 대기 가능한 댓글과 활동 알림의 합계',
            min: 1,
            max: 10000,
            step: '1',
        },
        {
            key: 'mock_interval_seconds',
            label: '데모 댓글 간격 (초)',
            hint: '데모 댓글과 활동 알림을 생성하는 간격',
            min: 0.001,
            max: 3600,
            step: 'any',
        },
        {
            key: 'tiktok_reconnect_min_seconds',
            label: '재연결 최소 간격 (초)',
            hint: '실제 방송 연결 재시도 간격',
            min: 0.001,
            max: 300,
            step: 'any',
        },
        {
            key: 'tiktok_reconnect_max_seconds',
            label: '재연결 최대 간격 (초)',
            hint: '최소 간격 이상으로 설정',
            min: 0.001,
            max: 3600,
            step: 'any',
        },
    ];
    const visibleFields = fields.filter((field) =>
        mode === 'tiktok'
            ? field.key !== 'mock_interval_seconds'
            : !field.key.startsWith('tiktok_'),
    );
    const basicFields = visibleFields.filter((field) =>
        ['comment_history_size', 'mock_interval_seconds'].includes(field.key),
    );
    const advancedFields = visibleFields.filter((field) => !basicFields.includes(field));
    const logOptions = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'].map((value) => ({
        value,
        text: value,
    }));

    const controller = new AbortController();
    async function loadConfig() {
        error = '';
        loading = true;
        try {
            const response = await requestJson(
                '/config',
                { signal: controller.signal, cache: 'no-store' },
                5000,
            );
            if (!response.ok) throw new Error('Configuration unavailable');
            const config = response.data;
            if (typeof config !== 'object' || config === null)
                throw new Error('Invalid configuration');
            if (!('session_id' in config) || config.session_id !== sessionId) {
                error = '다른 화면에서 상태가 변경되었습니다. 닫은 뒤 다시 열어주세요.';
                return;
            }
            const record = config as Record<string, unknown>;
            if (
                !fields.every(
                    (field) =>
                        typeof record[field.key] === 'number' && Number.isFinite(record[field.key]),
                ) ||
                !logOptions.some((option) => option.value === record.log_level)
            )
                throw new Error('Invalid configuration');
            values = Object.fromEntries(
                fields.map((field) => [field.key, String(record[field.key])]),
            );
            logLevel = String(record.log_level);
            loading = false;
        } catch {
            if (!controller.signal.aborted)
                error = '설정을 불러오지 못했습니다. 연결 상태를 확인하고 다시 시도해주세요.';
        }
    }
    onMount(() => {
        void loadConfig();
        return () => controller.abort();
    });

    function revealInvalidField(event: Event) {
        if (!(event.target instanceof HTMLInputElement)) return;
        // Open synchronously so native form validation can focus the invalid input.
        event.target.closest('details')?.setAttribute('open', '');
        error = '입력값을 확인해주세요. 각 항목의 허용 범위 안에서 입력해야 합니다.';
    }

    async function apply(event: SubmitEvent) {
        event.preventDefault();
        if (blocked || loading) return;
        error = '';
        if (
            mode === 'tiktok' &&
            Number(values.tiktok_reconnect_max_seconds) <
                Number(values.tiktok_reconnect_min_seconds)
        ) {
            advanced.open = true;
            error = '재연결 최대 간격은 최소 간격 이상이어야 합니다.';
            (event.currentTarget as HTMLFormElement)
                .querySelector<HTMLInputElement>('[name="tiktok_reconnect_max_seconds"]')
                ?.focus();
            return;
        }
        saving = true;
        try {
            const settings = {
                ...Object.fromEntries(
                    visibleFields.map((field) => [field.key, Number(values[field.key])]),
                ),
                log_level: logLevel,
            };
            const problem = await onapply(settings, sessionId);
            if (problem) {
                error = problem;
                return;
            }
            open = false;
        } catch {
            error = '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.';
        } finally {
            saving = false;
        }
    }
</script>

{#snippet numberField(field: (typeof fields)[number])}
    <div class="setting-field">
        <TextFieldOutlined
            label={field.label}
            name={field.key}
            type="number"
            bind:value={values[field.key]}
            min={field.min}
            max={field.max}
            step={field.step}
            required
            disabled={loading || blocked}
            aria-describedby={field.key + '-hint'}
        />
        <p id={field.key + '-hint'}>{field.hint} · {field.min}–{field.max}</p>
    </div>
{/snippet}

<Dialog
    headline={title}
    bind:open
    {onclose}
    role="dialog"
    aria-label={title}
    closedby={saving ? 'none' : 'any'}
    oncancel={(event: Event) => {
        if (saving) event.preventDefault();
    }}
    style="width: min(42rem, calc(100vw - 32px)); max-width: 42rem; max-height: calc(100dvh - 32px);"
>
    <form
        id="monitor-settings"
        class="settings-form"
        onsubmit={apply}
        oninvalidcapture={revealInvalidField}
    >
        <p>
            적용하면 기존 목록을 비우고 새 설정으로 다시 연결합니다.<br />변경값은 서버를 재시작할
            때까지 유지됩니다.
        </p>
        {#if loading && !error}<p role="status">설정을 불러오는 중…</p>{/if}
        <p>모드·계정 변경은 모니터 종료 후 첫 화면에서 할 수 있습니다.</p>
        <div class="settings-grid">
            {#each basicFields as field (field.key)}{@render numberField(field)}{/each}
        </div>
        <details bind:this={advanced}>
            <summary>고급 설정</summary>
            <p class="advanced-hint">
                {mode === 'tiktok'
                    ? '수신 대기량, 로그 수준 및 연결 재시도 간격을 조정합니다.'
                    : '수신 대기량과 로그 수준을 조정합니다.'}
            </p>
            <div class="settings-grid">
                {#each advancedFields as field (field.key)}{@render numberField(field)}{/each}
                <div class="setting-field">
                    <SelectOutlined
                        label="로그 수준"
                        options={logOptions}
                        bind:value={logLevel}
                        width="100%"
                        disabled={loading || blocked}
                    />
                    <p>일반 운영은 INFO</p>
                </div>
            </div>
        </details>
        {#if error}<p class="settings-error" role="alert">{error}</p>{/if}
        {#if loading && error}<Button
                type="button"
                variant="text"
                disabled={blocked}
                onclick={loadConfig}>다시 불러오기</Button
            >{/if}
        {#if recoveryMessage}<p role="status">{recoveryMessage}</p>{/if}
    </form>
    {#snippet buttons()}
        <Button
            type="button"
            variant="text"
            size="m"
            disabled={saving}
            onclick={() => (open = false)}>{recoveryMessage ? '닫기' : '취소'}</Button
        >
        <Button type="submit" form="monitor-settings" size="m" disabled={loading || blocked}
            >{saving ? '적용 중…' : '적용'}</Button
        >
    {/snippet}
</Dialog>

<style>
    .settings-form {
        display: flex;
        flex-direction: column;
        gap: 24px;
    }
    .settings-form p {
        margin: 0;
        font-size: 0.8rem;
        line-height: 1.6;
    }
    .settings-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 24px;
    }
    .setting-field {
        display: flex;
        flex-direction: column;
        min-width: 0;
        gap: 10px;
    }
    .setting-field :global(.m3-container) {
        min-width: 0;
    }
    .setting-field p {
        font-size: 0.7rem;
    }
    .settings-error {
        color: var(--m3c-error);
    }
    details {
        border-top: 1px solid var(--m3c-outline-variant);
    }
    summary {
        padding: 16px 0;
        cursor: pointer;
        font-size: 0.85rem;
        font-weight: 700;
    }
    summary:focus-visible {
        outline: 2px solid var(--m3c-secondary);
        outline-offset: 4px;
        border-radius: 4px;
    }
    .settings-form .advanced-hint {
        margin-bottom: 24px;
        color: var(--m3c-on-surface-variant);
    }
    @media (width < 700px) {
        .settings-grid {
            grid-template-columns: 1fr;
        }
    }
</style>
