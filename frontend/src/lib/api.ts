// Covers both response headers and JSON body; always release the timer/listener.
export async function requestJson(path: string, init: RequestInit = {}, timeoutMs = 15_000): Promise<{
  ok: boolean; status: number; data: unknown;
}> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (init.signal?.aborted) abort();
  init.signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(abort, timeoutMs);
  try {
    const response = await fetch(path, { ...init, signal: controller.signal });
    const data: unknown = await response.json();
    return { ok: response.ok, status: response.status, data };
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener('abort', abort);
  }
}
