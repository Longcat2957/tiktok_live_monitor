# Project guidance

- Read TIKTOK_LIVE_MONITOR_SPEC.md; keep the scope to one account, comments and LIVE activity. Persist comments and safe backend diagnostics in one SQLite archive; no activity/image persistence, replay, new archive API or automatic retention deletion.
- Backend: Python 3.14+, FastAPI lifespan, bounded queues. Keep TikTok APIs in integrations/tiktok.py.
- Backend boundaries: `api/routers` handles HTTP/WS, `schemas` defines contracts, `services/monitor.py` owns session transitions, `realtime/broadcaster.py` owns browser delivery. Use the shared MonitorService dependency; keep routes out of worker internals.
- Frontend: Svelte 5 + strict TypeScript, static adapter, same-origin WebSocket; plain text comments.
- Frontend boundaries: `+page.svelte` composes the screen; components own their UI, drafts and scoped CSS. `lib/monitor/session.svelte.ts` owns WS/feed state, `commands.svelte.ts` owns HTTP changes and recovery. Create state per page and dispose connections, requests, timers and queued frames on unmount.
- Import Svelte rune modules with explicit `.svelte.js` paths; reserve `.svelte` imports for components.
- Frontend style: use ESLint recommended JavaScript/TypeScript/Svelte rules and Prettier with 4-space indentation, no tabs. Use `pnpm lint:fix` and `pnpm format` for automatic corrections.
- Preserve receive order. Never let a slow browser block the source or another browser.
- Use uv and pnpm lockfiles. Verify backend pytest/mypy and frontend lint/format:check/check/test/build after meaningful changes.
- Test mock mode without TikTok credentials. Do not log event payloads or secrets.
- Archive records before the display queue can drop them; keep one bounded writer queue outside session transitions. Use the SQLite backup API for external snapshots, not a live DB file copy.
- Keep deployment single-container, non-root, localhost-only; Chromium belongs on the host.
