# Project guidance

- Read TIKTOK_LIVE_MONITOR_SPEC.md; keep the scope to one account, comments only, no persistence.
- Backend: Python 3.11+, FastAPI lifespan, bounded queues. Keep TikTok APIs in sources/tiktok.py.
- Frontend: Svelte 5 + strict TypeScript, static adapter, same-origin WebSocket; plain text comments.
- Preserve receive order. Never let a slow browser block the source or another browser.
- Use uv and pnpm lockfiles. Verify backend pytest/mypy and frontend check/test/build after meaningful changes.
- Test mock mode without TikTok credentials. Do not log event payloads or secrets.
- Keep deployment single-container, non-root, localhost-only; Chromium belongs on the host.
