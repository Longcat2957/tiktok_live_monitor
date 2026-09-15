<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { Button, ConnectedButtons, TextFieldOutlined } from 'm3-svelte';
  import SettingsDialog from '$lib/components/SettingsDialog.svelte';
  import ToolbarButton from '$lib/components/ToolbarButton.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import FontScaleControl from '$lib/components/FontScaleControl.svelte';
  import { requestJson } from '$lib/api';
  import { monitorView } from '$lib/monitor-state';
  import CommentList from '$lib/components/CommentList.svelte';
  import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
  import AccountChip from '$lib/components/AccountChip.svelte';
  import { DEFAULT_HISTORY_SIZE } from '$lib/config';
  import { appendComment } from '$lib/history';
  import { connectMonitor, websocketUrl } from '$lib/websocket';
  import { parseMessage, type BackendState, type FeedMessage, type Source, type StatusMessage } from '$lib/types';

  let comments = $state<FeedMessage[]>([]);
  let fontScale = $state(100);
  let backend = $state<BackendState>('connecting');
  let source = $state<StatusMessage | null>(null);
  let limit = DEFAULT_HISTORY_SIZE;
  let sessionId = $state<string | null>(null);
  let account = $state('');
  let mode = $state<Source>('tiktok');
  let editing = $state(false);
  let showSetup = $derived(source?.state === 'idle');
  let saving = $state(false);
  let error = $state('');
  let actionError = $state('');
  let checking = $state(false);
  let pendingSession = $state<string | null>(null);
  let recoveryMessage = $state('');
  let blocked = $derived(saving || pendingSession !== null);
  let view = $derived(monitorView(backend, source));
  const number = new Intl.NumberFormat('ko-KR');
  const requests = new AbortController();
  let previousSetup: boolean | undefined;

  $effect(() => {
    if (!source || blocked || editing) return;
    const setup = showSetup;
    const changed = previousSetup !== undefined && previousSetup !== setup;
    previousSetup = setup;
    if (changed) void tick().then(() => {
      const target = setup
        ? document.querySelector<HTMLElement>('.account-field input:not(:disabled)') ?? document.querySelector<HTMLElement>('.account-panel input[type="radio"]:checked')
        : document.getElementById('monitor-title');
      target?.focus({ preventScroll: true });
    });
  });

  async function checkResult() {
    if (!pendingSession || checking) return;
    const expected = pendingSession;
    checking = true;
    try {
      const { data } = await requestJson('/health', { signal: requests.signal, cache: 'no-store' }, 5000);
      if (typeof data !== 'object' || data === null || !('source' in data) ||
        !('pending_commands' in data) || !Number.isInteger(data.pending_commands) || Number(data.pending_commands) < 0)
        throw new Error('Invalid server status');
      const snapshot = parseMessage(JSON.stringify(data.source));
      if (snapshot?.type !== 'status') throw new Error('Invalid server status');
      if (pendingSession !== expected) return;
      if (snapshot.session_id !== expected || data.pending_commands === 0) {
        pendingSession = null;
        recoveryMessage = snapshot.session_id !== expected
          ? '서버의 상태 변경을 확인했습니다. 현재 화면을 확인해주세요.'
          : '서버가 현재 처리 중인 요청은 없습니다. 상태 변경이 필요하면 다시 시도해주세요.';
      } else {
        recoveryMessage = '서버에서 요청을 처리 중입니다. 완료될 때까지 중복 요청을 보내지 않습니다.';
      }
      // WebSocket alone applies session boundaries, so older HTTP snapshots cannot
      // clear newer comments or admit old frames into a new session.
    } catch {
      if (!requests.signal.aborted && pendingSession === expected)
        recoveryMessage = '처리 결과를 확인할 수 없습니다. 연결이 복구되면 자동으로 다시 확인합니다.';
    } finally { checking = false; }
  }

  $effect(() => {
    if (pendingSession && !checking && !saving) {
      const timer = setTimeout(() => void checkResult(), 3000);
      return () => clearTimeout(timer);
    }
  });

  async function sendChange(path: string, method: string, body: Record<string, unknown>, expected: string): Promise<string | null> {
    if (blocked) return '이전 요청의 처리 결과를 확인하고 있습니다.';
    saving = true;
    recoveryMessage = '';
    try {
      const response = await requestJson(path, {
        method, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: expected, ...body }), signal: requests.signal
      });
      if (response.status === 409) return '다른 화면에서 상태가 변경되었습니다. 현재 상태를 확인하고 다시 시도해주세요.';
      if (response.status === 422) return '@아이디 또는 설정값의 허용 범위를 확인해주세요.';
      if (response.status >= 500) throw new Error('Server response uncertain');
      if (!response.ok) return '요청을 처리하지 못했습니다. 서버 상태를 확인하고 다시 시도해주세요.';
      return null;
    } catch {
      if (requests.signal.aborted) return '화면이 닫혀 요청 결과를 확인하지 못했습니다.';
      if (source && source.session_id !== expected) {
        recoveryMessage = '서버의 상태 변경을 확인했습니다. 현재 화면에 반영했습니다.';
        return '요청 응답을 받지 못했지만 서버의 현재 상태를 확인했습니다.';
      }
      pendingSession = expected;
      recoveryMessage = '요청 응답이 지연되어 처리 결과를 확인 중입니다…';
      await checkResult();
      return '요청 응답을 받지 못했습니다. 서버 상태 확인 안내를 참고해주세요.';
    } finally { saving = false; }
  }

  async function updateMonitor(refresh: boolean) {
    if (!source || source.state === 'idle' || blocked) return;
    actionError = '';
    const problem = await sendChange(refresh ? '/refresh' : '/account', refresh ? 'POST' : 'DELETE', {}, source.session_id);
    if (problem) {
      actionError = recoveryMessage ? problem : (refresh ? '새로고침하지 못했습니다. ' : '초기화하지 못했습니다. ') + problem;
    } else { editing = false; error = ''; }
  }

  async function selectAccount(event: SubmitEvent) {
    event.preventDefault();
    if (!source || blocked) return;
    error = '';
    const problem = await sendChange('/account', 'POST', { source: mode, username: mode === 'tiktok' ? account : '' }, source.session_id);
    if (problem) error = problem;
    else editing = false;
  }

  async function applySettings(settings: Record<string, unknown>, expected: string) {
    return sendChange('/config', 'PATCH', { settings }, expected);
  }
  onMount(() => {
    let pending: FeedMessage[] = [];
    let frame: number | undefined;
    function clearPending() {
      if (frame !== undefined) cancelAnimationFrame(frame);
      frame = undefined;
      pending = [];
    }
    const disconnect = connectMonitor(websocketUrl(window.location), (message) => {
      if (message.type !== 'status') {
        // Bound the waiting batch too: hidden tabs can suspend animation frames.
        pending = appendComment(pending, message, limit);
        frame ??= requestAnimationFrame(() => {
          frame = undefined;
          comments = pending.reduce((history, item) => appendComment(history, item, limit), comments);
          pending = [];
        });
      }
      else {
        limit = message.comment_history_size;
        if (sessionId !== message.session_id) {
          clearPending();
          comments = [];
          mode = message.source;
          account = message.username ?? '';
        }
        sessionId = message.session_id;
        source = message;
        if (pendingSession && message.session_id !== pendingSession) {
          pendingSession = null;
          actionError = '';
          error = '';
          recoveryMessage = '서버의 상태 변경을 확인했습니다. 현재 화면에 반영했습니다.';
        }
      }
    }, (state) => {
      backend = state;
    });
    return () => { requests.abort(); clearPending(); disconnect(); };
  });
</script>

<svelte:head><title>TikTok LIVE · 댓글 모니터</title><meta name="description" content="실시간 LIVE 댓글 모니터" /></svelte:head>

<main>
  <header class="monitor-header">
    <div class="wordmark" id="monitor-title" tabindex="-1"><span class="live-badge">LIVE</span><span>댓글 모니터</span></div>
    {#if source && source.state !== 'idle'}
      <div class="monitor-actions">
        <FontScaleControl bind:value={fontScale} />
        <ThemeToggle />
        <ToolbarButton label="모니터 설정" disabled={blocked} onclick={() => editing = true}>
          <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M4 7h9m4 0h3M4 17h3m4 0h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" />
          </svg>
        </ToolbarButton>
        <ToolbarButton label="댓글 비우기 · 다시 연결" disabled={blocked} onclick={() => updateMonitor(true)}>
          <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 10a9 9 0 1 0-2 8M21 4v6h-6" />
          </svg>
        </ToolbarButton>
        <ToolbarButton label="모니터 종료 · 처음으로" disabled={blocked} onclick={() => updateMonitor(false)}>
          <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 4H4v16h5M9 12h12m-4-4 4 4-4 4" />
          </svg>
        </ToolbarButton>
      </div>
    {:else}<div class="monitor-actions"><span class="header-note">YOUR LIVE. EVERY COMMENT.</span><ThemeToggle /></div>{/if}
  </header>
  {#if source && source.state !== 'idle'}
    <section class="live-summary" aria-label="방송 정보">
      {#key source.username}<AccountChip username={source.username} />{/key}
      <div class="live-metrics" aria-label="방송 통계" class:stale={backend !== 'connected' || source.state !== 'connected'}>
        <span>시청자 <strong>{source.live?.viewers == null ? '—' : number.format(source.live.viewers)}</strong></span>
        <span>좋아요 <strong>{source.live?.likes == null ? '—' : number.format(source.live.likes)}</strong></span>
      </div>
    </section>
  {/if}
  {#if actionError}<p class="action-error" role="alert">{actionError}</p>
  {:else if source?.state === 'error'}<p class="action-error" role="status">{source.message}</p>{/if}
  {#if recoveryMessage}
    <div class="recovery-notice">
      <p role="status">{recoveryMessage}</p>
      {#if pendingSession}<Button variant="text" size="s" disabled={checking} onclick={checkResult}>{checking ? '확인 중…' : '상태 다시 확인'}</Button>{/if}
    </div>
  {/if}
  {#if showSetup}
    <section class="account-panel" aria-labelledby="setup-title">
      <div class="setup-intro">
        <span class="eyebrow">READY WHEN YOU ARE</span>
        <h1 id="setup-title">지금, 시청자의<br /><span>이야기를 만나세요.</span></h1>
        <p>방송을 연결하거나 데모로 먼저 둘러보세요.</p>
      </div>
      <form onsubmit={selectAccount}>
        <fieldset disabled={blocked}>
          <legend>실행 모드</legend>
          <ConnectedButtons>
            <Button variant="tonal" size="m" square label>
              <input type="radio" name="mode" value="tiktok" bind:group={mode} onchange={() => error = ''} />실제 방송
            </Button>
            <Button variant="tonal" size="m" square label>
              <input type="radio" name="mode" value="mock" bind:group={mode} onchange={() => error = ''} />데모 체험
            </Button>
          </ConnectedButtons>
        </fieldset>
        <div class="mode-details">
          <div class="mode-content" aria-hidden={mode !== 'tiktok'} inert={mode !== 'tiktok'}>
            <div class="account-field">
              <TextFieldOutlined label="TikTok 아이디 또는 방송 주소" bind:value={account}
                required={mode === 'tiktok'} maxlength={256} autocomplete="off" autocapitalize="none" spellcheck="false"
                disabled={blocked || mode !== 'tiktok'} error={Boolean(error)} aria-invalid={Boolean(error)}
                aria-describedby={error ? 'account-hint account-error' : 'account-hint'} />
            </div>
            <p id="account-hint">@아이디 또는 TikTok 프로필·LIVE 주소를 입력하세요.<br />방송 전이라면 시작할 때까지 기다립니다.</p>
          </div>
          <div class="mode-content" aria-hidden={mode !== 'mock'} inert={mode !== 'mock'}>
            <div class="demo-description"><span class="demo-badge">DEMO</span><h2>방송 없이, 바로 체험.</h2></div>
            <p>가상의 댓글·선물·통계와 방송 상태를 확인하세요.<br />계정 입력이나 실제 방송 연결은 필요하지 않습니다.</p>
          </div>
        </div>
        {#if error}<p id="account-error" role="alert">{error}</p>{/if}
        <div class="account-actions">
          <Button type="submit" size="m" square disabled={blocked || backend !== 'connected'}>{saving ? '시작 준비 중…' : '시작'}</Button>
        </div>
        <p class="session-note">장비를 다시 켜면 모드를 선택하고 다시 시작해주세요.</p>
      </form>
    </section>
  {:else if comments.length === 0}
    <section class="empty" data-state={view.kind} role="status"><span class="eyebrow">LIVE MONITOR</span><h1>{view.title}</h1><p>{view.description}</p></section>
  {/if}
  {#if !showSetup && comments.length > 0}{#key sessionId}<CommentList {comments} {fontScale} />{/key}{/if}
  <footer>
    <p class="broadcast-state" data-state={view.tone} role="status" title={source?.state === 'idle' ? undefined : view.label}>{source?.state === 'idle' ? '' : view.label}</p>
    <ConnectionStatus {backend} />
  </footer>
</main>

{#if editing && source}
  <SettingsDialog {source} {blocked} {recoveryMessage} onapply={applySettings} onclose={() => editing = false} />
{/if}
