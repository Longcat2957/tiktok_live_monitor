"""Gift-image admission and coalescing through real localhost HTTP/WS sockets."""

import asyncio
import json
import socket
from contextlib import asynccontextmanager

import httpx
import uvicorn
from websockets.asyncio.client import connect

from app.config import Settings
from app.main import create_app
from app.schemas.events import Comment, User
from app.services.gift_images import MAX_DOWNLOADS, MAX_PENDING

PNG = b"\x89PNG\r\n\x1a\n" + b"offline-image-fixture"


async def eventually(predicate):
    # Bounds test completion; these are not endpoint latency targets.
    async with asyncio.timeout(5):
        while not predicate():
            await asyncio.sleep(0.002)


@asynccontextmanager
async def running_images(respond):
    app = create_app(Settings(_env_file=None, mock_interval_seconds=3600, log_level="WARNING"))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.setblocking(False)
    base = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", ws="websockets-sansio"))
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        await eventually(lambda: server.started or serving.done())
        assert server.started
        monitor = app.state.monitor
        monitor.gift_images.client = httpx.AsyncClient(
            transport=httpx.MockTransport(respond), trust_env=False
        )
        async with httpx.AsyncClient(
            base_url=base,
            headers={"Origin": base},
            timeout=5,
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=0),
            trust_env=False,
        ) as client:
            yield monitor, client, base
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(serving, 10)
        finally:
            listener.close()
    assert monitor.gift_images.closed and monitor.gift_images.pending == 0
    assert not monitor.gift_images.inflight
    assert monitor.gift_images.client.is_closed
    assert not monitor.broadcaster.tasks
    assert monitor.archive.get_health().queued == 0 and monitor.archive._executor is None


async def test_same_key_http_fanout_cancellation_and_conditional_get_keep_comments_flowing():
    release = asyncio.Event()
    calls = 0

    async def respond(_request):
        nonlocal calls
        calls += 1
        await release.wait()
        return httpx.Response(200, headers={"Content-Type": "image/png"}, content=PNG)

    async with running_images(respond) as (monitor, client, base):
        cache = monitor.gift_images
        path = cache.register("https://p16.tiktokcdn.com/shared-load.png")
        assert path is not None
        key = path.rsplit("/", 1)[1]
        tasks = []
        async with connect(base.replace("http:", "ws:") + "/ws", origin=base) as peer:
            initial = json.loads(await asyncio.wait_for(peer.recv(), 5))
            response = await client.post(
                "/account", json={"session_id": initial["session_id"], "source": "mock"}
            )
            assert response.status_code == 200
            await eventually(lambda: monitor.sink is not None and monitor.sink.active)
            try:
                admitted = [asyncio.create_task(client.get(path)) for _ in range(MAX_PENDING)]
                tasks.extend(admitted)
                await eventually(lambda: cache.pending == MAX_PENDING and calls == 1)
                download = cache.inflight[key]
                overflow = [asyncio.create_task(client.get(path)) for _ in range(MAX_PENDING)]
                tasks.extend(overflow)
                rejected = await asyncio.gather(*overflow)
                assert len(tasks) >= 32
                assert all(response.status_code == 404 for response in rejected)
                assert all(response.headers["cache-control"] == "no-store" for response in rejected)
                assert cache.pending == MAX_PENDING and len(cache.inflight) == 1
                assert calls == 1 and not download.done()

                cancelled = admitted[:4]
                for task in cancelled:
                    task.cancel()
                results = await asyncio.gather(*cancelled, return_exceptions=True)
                assert all(isinstance(result, asyncio.CancelledError) for result in results)
                # A disconnected TCP client need not cancel its server route. The shared
                # download must survive either server waiter outcome.
                assert cache.inflight[key] is download and not download.done()
                assert 0 <= cache.pending <= MAX_PENDING
                health, config = await asyncio.gather(client.get("/health"), client.get("/config"))
                assert health.status_code == config.status_code == 200
                assert health.json()["source"]["state"] == "connected"
                monitor.sink.publish(
                    Comment(
                        id="while-image-cdn-is-delayed",
                        user=User(nickname="Image load", unique_id="image-load"),
                        comment="Comment during delayed image download",
                    )
                )
                async with asyncio.timeout(5):
                    while True:
                        event = json.loads(await peer.recv())
                        if (
                            event["type"] == "comment"
                            and event["id"] == "while-image-cdn-is-delayed"
                        ):
                            break
                assert not release.is_set() and not download.done() and calls == 1

                release.set()
                images = await asyncio.gather(*admitted[4:])
                assert all(
                    response.status_code == 200 and response.content == PNG for response in images
                )
                await eventually(lambda: cache.pending == 0 and not cache.inflight)
                etag = images[0].headers["etag"]
                cached, unchanged = await asyncio.gather(
                    client.get(path), client.get(path, headers={"If-None-Match": etag})
                )
                assert cached.status_code == 200 and cached.content == PNG
                assert unchanged.status_code == 304 and unchanged.content == b""
                assert unchanged.headers["etag"] == etag
                assert unchanged.headers["x-content-type-options"] == "nosniff"
                assert unchanged.headers["cache-control"].startswith("public, max-age=")
                assert calls == 1
            finally:
                release.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)


async def test_distinct_image_keys_limit_downloads_and_pending_http_callers():
    release = asyncio.Event()
    started = active = peak = 0

    async def respond(_request):
        nonlocal started, active, peak
        started += 1
        active += 1
        peak = max(peak, active)
        try:
            await release.wait()
            return httpx.Response(200, headers={"Content-Type": "image/png"}, content=PNG)
        finally:
            active -= 1

    async with running_images(respond) as (monitor, client, _base):
        cache = monitor.gift_images
        paths = [
            cache.register(f"https://p16.tiktokcdn.com/distinct-{number}.png")
            for number in range(MAX_PENDING * 2)
        ]
        assert all(path is not None for path in paths)
        tasks = []
        try:
            admitted = [asyncio.create_task(client.get(path)) for path in paths[:MAX_PENDING]]
            tasks.extend(admitted)
            await eventually(
                lambda: (
                    cache.pending == MAX_PENDING
                    and len(cache.inflight) == MAX_PENDING
                    and active == MAX_DOWNLOADS
                )
            )
            assert started == MAX_DOWNLOADS
            overflow = [asyncio.create_task(client.get(path)) for path in paths[MAX_PENDING:]]
            tasks.extend(overflow)
            rejected = await asyncio.gather(*overflow)
            assert all(response.status_code == 404 for response in rejected)
            assert all(response.headers["cache-control"] == "no-store" for response in rejected)
            assert cache.pending == len(cache.inflight) == MAX_PENDING
            assert active == peak == MAX_DOWNLOADS

            release.set()
            images = await asyncio.gather(*admitted)
            assert all(
                response.status_code == 200 and response.content == PNG for response in images
            )
            await eventually(lambda: cache.pending == 0 and not cache.inflight)
            assert started == MAX_PENDING and peak == MAX_DOWNLOADS and active == 0
            # Admission rejection is temporary, so this registered key can be retried.
            retried = await client.get(paths[MAX_PENDING])
            assert retried.status_code == 200 and retried.content == PNG
            assert started == MAX_PENDING + 1 and peak <= MAX_DOWNLOADS
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
