"""Async service lookup stays available when unrelated sync workers are occupied."""

import asyncio
import json
from threading import Event

import anyio.to_thread
from websockets.asyncio.client import connect

from tests.api.test_network import eventually, running_monitor


async def test_http_and_websocket_lookup_do_not_wait_for_default_thread_pool(monkeypatch):
    async with running_monitor(monkeypatch) as (monitor, client, base):
        assert monitor.archive.get_health().ready
        limiter = anyio.to_thread.current_default_thread_limiter()
        original_tokens = limiter.total_tokens
        entered = [Event(), Event()]
        release = Event()
        workers = []

        def blocked_worker(started):
            started.set()
            assert release.wait(10), "Test must release its sync workers"

        async def admit_websocket():
            async with connect(
                base.replace("http:", "ws:") + "/ws",
                origin=base,
                proxy=None,
                open_timeout=3,
                close_timeout=1,
            ) as peer:
                status = json.loads(await asyncio.wait_for(peer.recv(), 3))
                assert status["type"] == "status" and status["state"] == "connected"
                return status["session_id"]

        try:
            assert limiter.borrowed_tokens == 0
            limiter.total_tokens = 2
            workers = [
                asyncio.create_task(anyio.to_thread.run_sync(blocked_worker, started))
                for started in entered
            ]
            await eventually(lambda: all(started.is_set() for started in entered))
            assert limiter.borrowed_tokens == limiter.total_tokens == 2

            # The bounds prevent a hang; both worker tokens remain held throughout
            # the actual TCP requests and WS handshake, rather than timing an SLA.
            health, config, websocket_session = await asyncio.wait_for(
                asyncio.gather(client.get("/health"), client.get("/config"), admit_websocket()), 3
            )
            assert health.status_code == config.status_code == 200
            assert health.json()["storage"]["ready"]
            assert health.json()["source"]["session_id"] == config.json()["session_id"]
            assert websocket_session == config.json()["session_id"]
            assert not release.is_set() and all(not worker.done() for worker in workers)
            assert limiter.borrowed_tokens == 2
        finally:
            release.set()
            try:
                await asyncio.wait_for(asyncio.gather(*workers), 5)
            finally:
                limiter.total_tokens = original_tokens
        assert limiter.borrowed_tokens == 0
