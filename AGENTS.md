# Project guidance

- Read TIKTOK_LIVE_MONITOR_SPEC.md; keep the scope to one TikTok account and one optional YouTube broadcast, comments and existing TikTok LIVE activity. Persist comments and safe backend diagnostics in one SQLite archive; no activity/image persistence, replay or new archive API. Apply 30-day retention only to live YouTube data (`source=youtube`); never expire TikTok or mock records.
- Backend: Python 3.14+, FastAPI lifespan, bounded queues. Keep TikTok APIs in integrations/tiktok.py.
- Backend boundaries: `api/routers` handles HTTP/WS, `schemas` defines contracts, `services/monitor.py` owns session transitions, `realtime/broadcaster.py` owns browser delivery. Use the shared MonitorService dependency; keep routes out of worker internals.
- Frontend: Svelte 5 + strict TypeScript, static adapter, same-origin WebSocket; plain text comments.
- Frontend boundaries: `+page.svelte` composes the screen; components own their UI, drafts and scoped CSS. `lib/monitor/session.svelte.ts` owns WS/feed state, `commands.svelte.ts` owns HTTP changes and recovery. Create state per page and dispose connections, requests, timers and queued frames on unmount.
- Import Svelte rune modules with explicit `.svelte.js` paths; reserve `.svelte` imports for components.
- Frontend style: use ESLint recommended JavaScript/TypeScript/Svelte rules and Prettier with 4-space indentation, no tabs. Use `pnpm lint:fix` and `pnpm format` for automatic corrections.
- Preserve receive order. Never let a slow browser block the source or another browser.
- Keep TikTok and YouTube receiver failures isolated. View selection (stacked split/side-by-side/combined/TikTok/YouTube) only changes browser presentation, never the running receivers. Split puts TikTok above or left of YouTube; bound feed and pending-frame history per platform.
- Use uv and pnpm lockfiles. Verify backend pytest/mypy and frontend lint/format:check/check/test/build after meaningful changes.
- Test mock mode without TikTok credentials. Do not log event payloads or secrets.
- Archive records before the display queue can drop them; keep one bounded writer queue outside session transitions. Use the SQLite backup API for external snapshots, not a live DB file copy.
- Keep deployment single-container, non-root, localhost-only; Chromium belongs on the host.
