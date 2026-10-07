"""Admission and churn invariants through real localhost HTTP/TCP WebSockets."""

import asyncio
import json

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from app.schemas.events import Comment, User
from tests.api.test_network import eventually, receive_comments, running_monitor


async def open_wave(endpoint, origin, count, opened):
    async def opening():
        try:
            peer = await connect(
                endpoint, origin=origin, open_timeout=3, close_timeout=0.5, ping_interval=None
            )
        except InvalidStatus as denied:
            # close(1013) before accept() is an HTTP denial, not a WS close frame.
            assert denied.response.status_code == 403
            return None
        opened.append(peer)
        async with asyncio.timeout(3):
            assert json.loads(await peer.recv())["type"] == "status"
        return peer

    results = await asyncio.gather(*(opening() for _ in range(count)), return_exceptions=True)
    for result in results:
        assert not isinstance(result, BaseException), repr(result)
    return [peer for peer in results if peer is not None]


async def publish(monitor, prefix, count, started=None):
    for index in range(count):
        monitor.sink.publish(
            Comment(
                id=f"{prefix}-{index}",
                user=User(nickname="test", unique_id="test"),
                comment="ordered comment",
            )
        )
        if started is not None:
            started.set()
        await asyncio.sleep(0.002)


async def observe_capacity(broadcaster, samples):
    while True:
        # Includes reserved handshakes and senders removed from clients but still closing.
        samples.append(len(broadcaster.tasks) + broadcaster.accepting)
        await asyncio.sleep(0.001)


async def probe_health(client, limit):
    for _ in range(5):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["websocket_connections"] <= limit
        await asyncio.sleep(0.01)


async def close_wave(peers):
    async def closing(index, peer):
        if index % 2:
            peer.transport.abort()
            await peer.wait_closed()
        else:
            await peer.close()

    async with asyncio.timeout(3):
        await asyncio.gather(*(closing(index, peer) for index, peer in enumerate(peers)))


@pytest.mark.parametrize("attempts", [32, 64])
async def test_simultaneous_ws_admission_is_bounded_and_keeps_existing_feed(monkeypatch, attempts):
    async with running_monitor(monkeypatch) as (monitor, client, base):
        manager = monitor.broadcaster
        assert manager.max_clients == 16
        endpoint = base.replace("http:", "ws:") + "/ws"
        opened, samples = [], []
        observer = asyncio.create_task(observe_capacity(manager, samples))
        producer = receiver = None
        try:
            healthy = (await open_wave(endpoint, base, 1, opened))[0]
            receiver = asyncio.create_task(receive_comments(healthy, 200))
            producer = asyncio.create_task(publish(monitor, "limit", 200))
            admitted, _ = await asyncio.gather(
                open_wave(endpoint, base, attempts, opened),
                probe_health(client, manager.max_clients),
            )
            assert len(admitted) == 15
            assert len(manager.clients) == 16
            assert max(samples) == 16
            await producer
            assert await receiver == [f"limit-{index}" for index in range(200)]
            assert monitor.broadcaster.dropped_comments == 0
            assert monitor.broadcaster.slow_disconnects == 0
            await close_wave(admitted)
            await eventually(
                lambda: len(manager.clients) == len(manager.tasks) == 1 and manager.accepting == 0
            )
            monitor.sink.publish(
                Comment(id="after-limit", user=User(nickname="test", unique_id="test"), comment="x")
            )
            assert await receive_comments(healthy, 1) == ["after-limit"]
            assert (await client.get("/health")).json()["websocket_connections"] == 1
            assert max(samples) <= manager.max_clients
        finally:
            for task in (observer, producer, receiver):
                if task is not None:
                    task.cancel()
            await asyncio.gather(
                *(task for task in (observer, producer, receiver) if task is not None),
                return_exceptions=True,
            )
            await asyncio.gather(*(peer.close() for peer in opened))
        await eventually(
            lambda: not manager.tasks and not manager.clients and manager.accepting == 0
        )


async def test_real_ws_reconnect_and_abrupt_close_waves_do_not_leak_or_interrupt_feed(monkeypatch):
    async with running_monitor(monkeypatch) as (monitor, client, base):
        manager = monitor.broadcaster
        endpoint = base.replace("http:", "ws:") + "/ws"
        opened, samples = [], []
        observer = asyncio.create_task(observe_capacity(manager, samples))
        receiver = producer = None
        try:
            healthy = (await open_wave(endpoint, base, 1, opened))[0]
            peers = await open_wave(endpoint, base, 15, opened)
            assert len(peers) == 15
            receiver = asyncio.create_task(receive_comments(healthy, 300))
            for wave in range(3):
                started = asyncio.Event()
                producer = asyncio.create_task(publish(monitor, f"wave-{wave}", 100, started))
                await started.wait()
                assert not producer.done()
                _, peers, _ = await asyncio.gather(
                    close_wave(peers),
                    open_wave(endpoint, base, 32, opened),
                    probe_health(client, manager.max_clients),
                )
                if not peers:
                    # Closing senders still occupy slots, so the overlapping wave may
                    # all be denied. Prove readmission once those slots are released.
                    await eventually(
                        lambda: (
                            len(manager.clients) == len(manager.tasks) == 1
                            and manager.accepting == 0
                        )
                    )
                    peers = await open_wave(endpoint, base, 32, opened)
                    assert len(peers) == 15
                assert 0 < len(peers) <= 15
                await producer
                await eventually(
                    lambda: (
                        len(manager.clients) == len(manager.tasks) == 1 + len(peers)
                        and manager.accepting == 0
                    )
                )
            assert await receiver == [
                f"wave-{wave}-{index}" for wave in range(3) for index in range(100)
            ]
            await close_wave(peers)
            await eventually(
                lambda: len(manager.clients) == len(manager.tasks) == 1 and manager.accepting == 0
            )
            assert max(samples) == manager.max_clients
            assert monitor.broadcaster.dropped_comments == 0
            assert monitor.broadcaster.slow_disconnects == 0
            assert (await client.get("/health")).status_code == 200
        finally:
            for task in (observer, producer, receiver):
                if task is not None:
                    task.cancel()
            await asyncio.gather(
                *(task for task in (observer, producer, receiver) if task is not None),
                return_exceptions=True,
            )
            await asyncio.gather(*(peer.close() for peer in opened))
        await eventually(
            lambda: not manager.tasks and not manager.clients and manager.accepting == 0
        )


@pytest.mark.parametrize(
    ("payload", "expected_close"),
    [("browser input", 1008), (b"binary input", 1008), (b"x" * 65536, 1009)],
    ids=["text", "binary", "64k-binary"],
)
async def test_server_only_ws_rejects_text_binary_and_bounded_large_frame(
    monkeypatch, payload, expected_close
):
    async with running_monitor(monkeypatch) as (monitor, client, base):
        endpoint = base.replace("http:", "ws:") + "/ws"
        async with connect(endpoint, origin=base) as healthy:
            await healthy.recv()
            async with connect(endpoint, origin=base) as sending:
                await sending.recv()
                await sending.send(payload)
                async with asyncio.timeout(3):
                    with pytest.raises(ConnectionClosed) as closed:
                        await sending.recv()
                assert closed.value.rcvd is not None and closed.value.rcvd.code == expected_close
            await eventually(
                lambda: len(monitor.broadcaster.clients) == len(monitor.broadcaster.tasks) == 1
            )
            monitor.sink.publish(
                Comment(id="after-input", user=User(nickname="test", unique_id="test"), comment="x")
            )
            assert await receive_comments(healthy, 1) == ["after-input"]
            assert (await client.get("/health")).status_code == 200
