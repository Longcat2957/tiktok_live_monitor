import asyncio
import socket
from collections import Counter

import httpx
import pytest
import uvicorn

from app.config import Settings
from app.main import create_app


async def wait_until(predicate, timeout=5):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.001)


@pytest.fixture
async def api_server(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            archive_path=tmp_path / "monitor.sqlite3",
            static_dir=tmp_path / "no-ui",
            mock_interval_seconds=3600,
            comment_history_size=30,
            log_level="WARNING",
        )
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.setblocking(False)
    base = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="warning", ws="websockets-sansio", timeout_keep_alive=30)
    )
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        await wait_until(lambda: server.started or serving.done())
        assert server.started, "HTTP server failed to start"
        async with httpx.AsyncClient(
            base_url=base,
            headers={"Origin": base},
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=64),
            timeout=20,
        ) as client:
            sid = (await client.get("/config")).json()["session_id"]
            started = await client.post("/account", json={"session_id": sid, "source": "mock"})
            assert started.status_code == 200
            monitor = app.state.monitor
            await wait_until(lambda: monitor.broadcaster.status.state == "connected")
            yield monitor, client, server
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(serving, timeout=10)
        finally:
            listener.close()
    monitor = app.state.monitor
    assert monitor.closed and not monitor.commands and not monitor.broadcaster.tasks
    assert monitor.supervisor_task is None and monitor.stream_task is None
    assert monitor.consumer_task is None and monitor.archive._executor is None
    storage = monitor.archive.get_health()
    assert storage.queued == 0 and storage.dropped == 0 and storage.error is None
    assert not server.server_state.tasks and not server.server_state.connections


def mutations(sid):
    return [
        ("POST", "/account", {"session_id": sid, "source": "mock"}),
        ("POST", "/refresh", {"session_id": sid}),
        ("PATCH", "/config", {"session_id": sid, "settings": {"comment_history_size": 31}}),
        ("DELETE", "/account", {"session_id": sid}),
    ]


async def test_mixed_http_command_storm_enforces_pending_limit_and_keeps_reads_responsive(
    api_server,
):
    monitor, client, _ = api_server
    sid = (await client.get("/config")).json()["session_id"]
    operations = mutations(sid) * 4
    requests = []
    await monitor.lock.acquire()
    lock_held = True
    try:
        accepted = [
            asyncio.create_task(client.request(method, path, json=body))
            for method, path, body in operations
        ]
        requests.extend(accepted)
        await wait_until(lambda: len(monitor.commands) == 16)
        assert all(not request.done() for request in accepted)
        # All four methods have accepted requests waiting; the next 16 arrive over TCP.
        overloaded = [
            asyncio.create_task(client.request(method, path, json=body))
            for method, path, body in operations
        ]
        requests.extend(overloaded)
        rejected = await asyncio.wait_for(asyncio.gather(*overloaded), timeout=5)
        assert [response.status_code for response in rejected] == [503] * 16
        assert all(set(response.json()) == {"detail"} for response in rejected)
        read_paths = ["/health", "/config"] * 16
        reads = await asyncio.wait_for(
            asyncio.gather(*(client.get(path) for path in read_paths)), timeout=5
        )
        assert all(response.status_code == 200 for response in reads)
        for path, response in zip(read_paths, reads, strict=True):
            body = response.json()
            if path == "/health":
                assert body["pending_commands"] == 16
                assert body["source"]["session_id"] == sid
            else:
                assert body["session_id"] == sid and body["comment_history_size"] == 30
        assert len(monitor.commands) == 16 and all(not request.done() for request in accepted)
        monitor.lock.release()
        lock_held = False
        completed = await asyncio.wait_for(asyncio.gather(*accepted), timeout=5)
        assert Counter(response.status_code for response in completed) == {200: 1, 409: 15}
        winner = next(
            index for index, response in enumerate(completed) if response.status_code == 200
        )
        current = completed[winner].json()["session_id"]
        assert current != sid
        await wait_until(lambda: not monitor.commands)
        health, config = await asyncio.gather(client.get("/health"), client.get("/config"))
        assert health.status_code == config.status_code == 200
        assert health.json()["pending_commands"] == 0
        assert health.json()["source"]["session_id"] == config.json()["session_id"] == current
        assert config.json()["comment_history_size"] == (31 if winner % 4 == 2 else 30)
    finally:
        if lock_held:
            monitor.lock.release()
        await asyncio.wait_for(asyncio.gather(*requests, return_exceptions=True), timeout=5)


async def test_invalid_stale_and_forbidden_http_floods_do_not_change_session(api_server):
    monitor, client, _ = api_server
    initial = (await client.get("/config")).json()
    sid = initial["session_id"]
    invalid = [
        ("POST", "/account", {"session_id": sid, "source": "invalid"}),
        ("POST", "/refresh", {"session_id": ""}),
        ("PATCH", "/config", {"session_id": sid, "settings": []}),
        ("DELETE", "/account", {"session_id": "x" * 65}),
    ] * 8
    await monitor.lock.acquire()
    try:
        responses = await asyncio.wait_for(
            asyncio.gather(
                *(client.request(method, path, json=body) for method, path, body in invalid)
            ),
            timeout=5,
        )
        assert [response.status_code for response in responses] == [422] * 32
        assert not monitor.commands
    finally:
        monitor.lock.release()
    stale = await asyncio.wait_for(
        asyncio.gather(
            *(
                client.request(method, path, json=body)
                for method, path, body in mutations("stale-session") * 4
            )
        ),
        timeout=5,
    )
    assert [response.status_code for response in stale] == [409] * 16
    runtime_invalid = await asyncio.wait_for(
        asyncio.gather(
            *(
                client.patch(
                    "/config", json={"session_id": sid, "settings": {"comment_queue_size": 0}}
                )
                for _ in range(16)
            )
        ),
        timeout=5,
    )
    assert [response.status_code for response in runtime_invalid] == [422] * 16
    forbidden = await asyncio.wait_for(
        asyncio.gather(
            *(
                client.request(method, path, json=body, headers={"Origin": "https://invalid.test"})
                for method, path, body in mutations(sid) * 4
            )
        ),
        timeout=5,
    )
    assert [response.status_code for response in forbidden] == [403] * 16
    unsupported = await asyncio.wait_for(
        asyncio.gather(
            *(
                client.request(method, path)
                for method, path in [
                    ("POST", "/health"),
                    ("PUT", "/account"),
                    ("DELETE", "/config"),
                    ("GET", "/refresh"),
                ]
                * 4
            )
        ),
        timeout=5,
    )
    assert [response.status_code for response in unsupported] == [405] * 16
    health, config = await asyncio.gather(client.get("/health"), client.get("/config"))
    assert health.status_code == config.status_code == 200
    assert health.json()["pending_commands"] == 0 and not monitor.commands
    assert config.json() == initial
    assert health.json()["source"]["session_id"] == sid


async def test_disconnected_http_client_does_not_cancel_an_accepted_transition(api_server):
    monitor, client, server = api_server
    sid = (await client.get("/config")).json()["session_id"]
    await monitor.lock.acquire()
    lock_held = True
    request = asyncio.create_task(client.request("DELETE", "/account", json={"session_id": sid}))
    try:
        await wait_until(lambda: len(monitor.commands) == 1)
        command = next(iter(monitor.commands))
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        await wait_until(lambda: not server.server_state.connections)
        assert command in monitor.commands and not command.done()
        monitor.lock.release()
        lock_held = False
        stopped = await asyncio.wait_for(asyncio.shield(command), timeout=5)
        assert stopped.state == "idle" and stopped.session_id != sid
        health, config = await asyncio.gather(client.get("/health"), client.get("/config"))
        assert health.status_code == config.status_code == 200
        assert health.json()["pending_commands"] == 0
        assert config.json()["session_id"] == stopped.session_id
        restarted = await client.post(
            "/account", json={"session_id": stopped.session_id, "source": "mock"}
        )
        assert restarted.status_code == 200 and restarted.json()["session_id"] != stopped.session_id
    finally:
        if lock_held:
            monitor.lock.release()
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)


@pytest.mark.parametrize("guard", ["fault", "storage_error", "storage_not_ready", "closed"])
async def test_health_stays_available_between_workers_but_transition_preserves_error_guards(
    api_server, monkeypatch, guard
):
    monitor, client, _ = api_server
    initial = (await client.get("/health")).json()
    sid = initial["source"]["session_id"]
    old_supervisor = monitor.supervisor_task
    assert old_supervisor is not None and not old_supervisor.done()
    entered, release = asyncio.Event(), asyncio.Event()
    original_stop = monitor._stop_session

    async def stopped_workers():
        result = await original_stop()
        assert result and old_supervisor.done()
        entered.set()
        await asyncio.wait_for(release.wait(), 5)
        return result

    monkeypatch.setattr(monitor, "_stop_session", stopped_workers)
    request = asyncio.create_task(client.post("/refresh", json={"session_id": sid}))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert monitor.supervisor_task is None and monitor._transitioning
        assert not request.done()
        health, config = await asyncio.gather(client.get("/health"), client.get("/config"))
        assert health.status_code == config.status_code == 200
        body = health.json()
        assert body["source"]["state"] == "connected"
        assert body["source"]["session_id"] == config.json()["session_id"] == sid
        assert body["pending_commands"] == 1 and body["fault"] is None
        assert body["storage"]["ready"] and body["storage"]["error"] is None

        with monkeypatch.context() as injected:
            if guard == "fault":
                injected.setattr(monitor, "fault", "shutdown_timeout")
            elif guard == "storage_error":
                injected.setattr(monitor.archive, "_error", "write:OperationalError")
            elif guard == "storage_not_ready":
                injected.setattr(monitor.archive, "_ready", False)
            else:
                injected.setattr(monitor, "closed", True)
            unavailable = await client.get("/health")
            assert unavailable.status_code == 503
            assert unavailable.json()["status"] == "error"
            assert monitor._transitioning and not request.done()
        assert (await client.get("/health")).status_code == 200
        release.set()
        refreshed = await asyncio.wait_for(request, 5)
        assert refreshed.status_code == 200 and refreshed.json()["session_id"] != sid
        await wait_until(lambda: not monitor.commands)
        assert not monitor._transitioning
        assert monitor.supervisor_task is not None and not monitor.supervisor_task.done()
        assert (await client.get("/health")).status_code == 200
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), 5)


async def test_cancelled_transition_clears_flag_and_exposes_unexpected_worker_absence(
    api_server, monkeypatch
):
    monitor, client, _ = api_server
    sid = (await client.get("/config")).json()["session_id"]
    entered, release = asyncio.Event(), asyncio.Event()
    old_supervisor = monitor.supervisor_task
    original_stop = monitor._stop_session

    async def stopped_workers():
        result = await original_stop()
        assert result and old_supervisor is not None and old_supervisor.done()
        entered.set()
        await asyncio.wait_for(release.wait(), 5)
        return result

    monkeypatch.setattr(monitor, "_stop_session", stopped_workers)
    changing = asyncio.create_task(monitor.refresh(sid))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert monitor._transitioning and monitor.supervisor_task is None
        assert (await client.get("/health")).status_code == 200
        command = next(iter(monitor.commands))
        command.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(changing, 5)
        await wait_until(lambda: not monitor.commands)
        assert not monitor._transitioning
        health = await client.get("/health")
        assert health.status_code == 503
        body = health.json()
        assert body["source"]["session_id"] == sid and body["source"]["state"] == "connected"
        assert body["pending_commands"] == 0 and body["fault"] is None
        assert body["storage"]["ready"] and body["storage"]["error"] is None
        # Worker absence is now unexpected, so it must remain unhealthy until recovery.
        release.set()
        stopped = await client.request("DELETE", "/account", json={"session_id": sid})
        assert stopped.status_code == 200 and stopped.json()["state"] == "idle"
        assert not monitor._transitioning
        assert (await client.get("/health")).status_code == 200
    finally:
        release.set()
        changing.cancel()
        await asyncio.gather(changing, return_exceptions=True)
