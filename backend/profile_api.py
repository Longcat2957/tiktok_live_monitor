"""Measure real HTTP/WS load with the app and load generator in separate processes.

Run from backend/: python profile_api.py --mode read --concurrency 16
Only a temporary localhost server, synthetic comments and an offline cached image are used.
"""

import argparse
import asyncio
import json
import math
import os
import socket
import sqlite3
import subprocess
import sys
import time
from collections import Counter, deque
from contextlib import AsyncExitStack, closing
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
import uvicorn
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from app.config import Settings
from app.main import create_app
from app.schemas.events import Comment, User
from app.services.archive import Archive
from app.services.gift_images import CachedImage
from profile_pipeline import percentile_ms
from stress_pipeline import PipelineProfile, ThreadProfile, profile_summary

SAMPLES = 10_000


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


@dataclass
class Metric:
    count: int = 0
    statuses: Counter = field(default_factory=Counter)
    errors: Counter = field(default_factory=Counter)
    latencies: deque = field(default_factory=lambda: deque(maxlen=SAMPLES))
    total_ns: int = 0
    max_ns: int = 0

    def record(self, started: int, status: int | None, error: str | None = None) -> None:
        elapsed = time.perf_counter_ns() - started
        self.count += 1
        self.total_ns += elapsed
        self.max_ns = max(self.max_ns, elapsed)
        self.latencies.append(elapsed)
        if status is not None:
            self.statuses[status] += 1
        if error is not None:
            self.errors[error] += 1

    def report(self, elapsed: float) -> dict:
        return {
            "count": self.count,
            "requests_per_second": round(self.count / elapsed, 2),
            "statuses": dict(self.statuses),
            "errors": dict(self.errors),
            "latency_ms": {f"p{p}": percentile_ms(list(self.latencies), p) for p in (50, 95, 99)},
            "mean_ms": round(self.total_ns / max(1, self.count) / 1_000_000, 3),
            "max_ms": round(self.max_ns / 1_000_000, 3),
            "retained_samples": len(self.latencies),
        }


async def serve(args) -> None:
    directory = args.state_dir
    generated = 0
    ignored = 0
    profiler = PipelineProfile() if args.profile else None
    app = create_app(
        Settings(_env_file=None, archive_path=directory / "monitor.sqlite3", log_level="WARNING")
    )

    class Source:
        def __init__(self, sink):
            self.sink = sink

        async def run(self):
            nonlocal generated, ignored
            self.sink.status("connected", "Isolated API load source")
            started = asyncio.get_running_loop().time()
            sequence = 0
            user = User(nickname="Load", unique_id="load")
            while asyncio.get_running_loop().time() < started + args.duration:
                await asyncio.sleep(
                    max(
                        0,
                        started + sequence / args.comment_rate - asyncio.get_running_loop().time(),
                    )
                )
                if asyncio.get_running_loop().time() >= started + args.duration:
                    break
                before = self.sink.received_comments
                self.sink.publish(
                    Comment(id=f"load-{generated}", user=user, comment="x" * args.comment_size)
                )
                if self.sink.received_comments > before:
                    generated += 1
                else:
                    ignored += 1  # Late events at a cancelled session are intentionally rejected.
                sequence += 1
            write_json(directory / "source-finished.json", {"generated": generated})
            await asyncio.Event().wait()

    class ProfiledArchive(Archive):
        def _write(self, batch):
            assert profiler is not None
            return profiler.write(super()._write, batch)

    listener = socket.socket(fileno=args.fd)
    listener.setblocking(False)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            log_level="error",
            ws="websockets-sansio",
            ws_max_size=1024,
            forwarded_allow_ips="",
            timeout_graceful_shutdown=15,
        )
    )
    archive_patch = patch("app.services.monitor.Archive", new=ProfiledArchive) if profiler else None
    if archive_patch:
        archive_patch.start()
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if serving.done():
                    await serving
                    raise RuntimeError("Load server stopped before startup")
                await asyncio.sleep(0.01)
        monitor = app.state.monitor
        monitor._make_stream = Source
        image_path = monitor.gift_images.register("https://p16.tiktokcdn.com/load.gif")
        assert image_path is not None
        body = b"GIF89a" + bytes(16_384)
        expires = time.monotonic() + 3600
        monitor.gift_images._store(
            image_path.rsplit("/", 1)[1], CachedImage(body, "image/gif", '"load"', expires), expires
        )
        write_json(directory / "ready.json", {"image_path": image_path})
        if profiler:
            profiler.main.enable()
        await asyncio.to_thread(sys.stdin.readline)
        server.should_exit = True
        await asyncio.wait_for(serving, 20)
        if profiler:
            profiler.main.disable()
        storage = monitor.archive.get_health()
        with closing(
            sqlite3.connect((directory / "monitor.sqlite3").as_uri() + "?mode=ro", uri=True)
        ) as db:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            rows = 0
            in_order = True
            contiguous = True
            previous = -1
            for (event_id,) in db.execute("SELECT event_id FROM comments ORDER BY id"):
                number = int(event_id.removeprefix("load-"))
                in_order &= number > previous
                contiguous &= number == rows
                previous = number
                rows += 1
            diagnostic_counts = dict(
                db.execute("SELECT event, COUNT(*) FROM diagnostics GROUP BY event")
            )
        summary = {
            "generated": generated,
            "ignored_late_events": ignored,
            "sqlite_comments": rows,
            "missing_comments": generated - rows,
            "missing_diagnostics": storage.dropped - (generated - rows),
            "saved_diagnostics_by_event": diagnostic_counts,
            "sqlite_order": in_order,
            "sqlite_contiguous": contiguous,
            "integrity": integrity,
            "storage": storage.model_dump(),
            "source_drops": monitor.broadcaster.dropped_comments,
            "slow_disconnects": monitor.broadcaster.slow_disconnects,
            "fault": monitor.fault,
            "recoveries": monitor.recoveries,
            "event_loop": type(asyncio.get_running_loop()).__module__,
            "clean_shutdown": monitor.closed
            and not monitor.broadcaster.tasks
            and not monitor.broadcaster.clients
            and monitor.broadcaster.accepting == 0
            and not monitor.commands
            and monitor.archive._executor is None
            and storage.queued == 0
            and not monitor.stuck
            and not server.server_state.tasks
            and not server.server_state.connections,
        }
        if profiler:
            summary["profile"] = profiler.report()
            summary["profile"]["main"]["scope"] = (
                "server process after readiness, including shutdown; excludes load-generator CPU"
            )
        write_json(directory / "server-result.json", summary)
    finally:
        if profiler:
            profiler.main.disable()
        server.should_exit = True
        try:
            await asyncio.wait_for(serving, 20)
        finally:
            listener.close()
            if archive_patch:
                archive_patch.stop()


def process_sample(pid: int) -> tuple[float, int]:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    cpu = (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
    rss = int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    return cpu, rss


async def run_load(args) -> dict:
    changing_sessions = args.mode in {"mixed", "mixed-churn"}
    churning_peers = args.mode in {"churn", "mixed-churn"}
    metrics: dict[str, Metric] = {}
    handshake = Metric()
    health_failures: Counter = Counter()
    receiver_errors: Counter = Counter()
    driver_profile = ThreadProfile(timer=time.thread_time) if args.profile else None
    peer_stats = [dict(received=0, last=-1, in_order=True, gaps=0) for _ in range(args.clients)]
    ws_latencies: deque[int] = deque(maxlen=SAMPLES)
    peaks = dict(pending_commands=0, websocket_connections=0, storage_queued=0, rss_bytes=0)
    stop = asyncio.Event()
    temporary_path: Path
    with TemporaryDirectory(prefix="api-load-", dir=args.directory) as temporary:
        temporary_path = Path(temporary).resolve()
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        base = f"http://127.0.0.1:{listener.getsockname()[1]}"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--serve",
            "--fd",
            str(listener.fileno()),
            "--state-dir",
            str(temporary_path),
            "--duration",
            str(args.duration),
            "--comment-rate",
            str(args.comment_rate),
            "--comment-size",
            str(args.comment_size),
        ]
        if args.profile:
            command.append("--profile")
        with (temporary_path / "server.log").open("w+") as log:
            child = subprocess.Popen(
                command,
                cwd=Path(__file__).resolve().parent,
                pass_fds=(listener.fileno(),),
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=log,
                text=True,
            )
            listener.close()
            workers = []
            receivers = []
            try:
                async with asyncio.timeout(15):
                    while not (temporary_path / "ready.json").exists():
                        if child.poll() is not None:
                            log.seek(0)
                            raise RuntimeError(f"Load server failed: {log.read()[-2000:]}")
                        await asyncio.sleep(0.02)
                ready = json.loads((temporary_path / "ready.json").read_text())
                limits = httpx.Limits(
                    max_connections=args.concurrency + 4,
                    max_keepalive_connections=args.concurrency + 4,
                )
                async with httpx.AsyncClient(
                    base_url=base,
                    headers={"Origin": base},
                    limits=limits,
                    timeout=5,
                    trust_env=False,
                ) as client:
                    sid = (await client.get("/config")).json()["session_id"]
                    http_clients = []

                    async def receive(index, connection):
                        session = None
                        previous_session = None
                        async for raw in connection:
                            event = json.loads(raw)
                            if event["type"] == "status":
                                session = event["session_id"]
                            elif event["type"] == "comment":
                                from datetime import datetime

                                number = int(event["id"].removeprefix("load-"))
                                peer = peer_stats[index]
                                peer["in_order"] &= number > peer["last"]
                                if previous_session == session and number != peer["last"] + 1:
                                    peer["gaps"] += 1
                                previous_session = session
                                peer["last"] = number
                                peer["received"] += 1
                                sent = datetime.fromisoformat(
                                    event["received_at"].replace("Z", "+00:00")
                                )
                                ws_latencies.append(
                                    max(0, int((time.time() - sent.timestamp()) * 1e9))
                                )

                    async def receive_checked(index, connection):
                        try:
                            await receive(index, connection)
                            receiver_errors["unexpected_close"] += 1
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            receiver_errors[type(exc).__name__] += 1

                    async def request_worker(index):
                        nonlocal sid
                        image = ready["image_path"]
                        read = [("GET", "/health"), ("GET", "/config"), ("GET", image)]
                        mixed = [
                            ("POST", "/refresh"),
                            ("PATCH", "/config"),
                            ("DELETE", "/account"),
                            ("POST", "/account"),
                        ]
                        paths = read + (mixed if changing_sessions else [])
                        iteration = index
                        while not stop.is_set():
                            method, path = paths[iteration % len(paths)]
                            label = f"{method} " + ("/gift-images/{key}" if path == image else path)
                            metric = metrics.setdefault(label, Metric())
                            body = {"session_id": sid}
                            if method == "POST" and path == "/account":
                                body["source"] = "mock"
                            if method == "PATCH":
                                body["settings"] = {"comment_history_size": 30 + iteration % 2}
                            started = time.perf_counter_ns()
                            try:
                                response = await http_clients[index].request(
                                    method, path, json=body if method != "GET" else None
                                )
                                allowed = {200, 409, 503} if method != "GET" else {200}
                                metric.record(
                                    started,
                                    response.status_code,
                                    None
                                    if response.status_code in allowed
                                    else "unexpected_status",
                                )
                                if path == "/health":
                                    health = response.json()
                                    if response.status_code != 200:
                                        key = json.dumps(
                                            {
                                                "state": health["source"]["state"],
                                                "fault": health["fault"],
                                                "pending_commands": health["pending_commands"],
                                                "storage_ready": health["storage"]["ready"],
                                                "storage_error": health["storage"]["error"],
                                            },
                                            sort_keys=True,
                                        )
                                        health_failures[key] += 1
                                    for name in ("pending_commands", "websocket_connections"):
                                        peaks[name] = max(peaks[name], health[name])
                                    peaks["storage_queued"] = max(
                                        peaks["storage_queued"], health["storage"]["queued"]
                                    )
                                if response.status_code == 200 and path != image:
                                    sid = response.json().get("session_id", sid)
                            except httpx.HTTPError as exc:
                                metric.record(started, None, type(exc).__name__)
                            iteration += 1

                    async def reconnect_worker(index):
                        iteration = index
                        while not stop.is_set():
                            started = time.perf_counter_ns()
                            try:
                                async with connect(
                                    base.replace("http:", "ws:") + "/ws",
                                    origin=base,
                                    proxy=None,
                                    open_timeout=5,
                                    close_timeout=1,
                                ) as connection:
                                    initial = json.loads(
                                        await asyncio.wait_for(connection.recv(), 5)
                                    )
                                    handshake.record(
                                        started,
                                        101,
                                        None if initial["type"] == "status" else "invalid_initial",
                                    )
                                    await asyncio.sleep(0.02)
                                    if iteration % 2:
                                        connection.transport.abort()
                            except InvalidStatus as exc:
                                status = exc.response.status_code
                                handshake.record(
                                    started, status, None if status == 403 else "unexpected_status"
                                )
                            except Exception as exc:
                                handshake.record(started, None, type(exc).__name__)
                            iteration += 1

                    async with AsyncExitStack() as stack:
                        # One persistent pool per worker avoids HTTPX scanning every peer's
                        # connection on each request, which otherwise saturates the driver first.
                        for _ in range(args.concurrency):
                            http_clients.append(
                                await stack.enter_async_context(
                                    httpx.AsyncClient(
                                        base_url=base,
                                        headers={"Origin": base},
                                        limits=httpx.Limits(
                                            max_connections=1, max_keepalive_connections=1
                                        ),
                                        timeout=5,
                                        trust_env=False,
                                    )
                                )
                            )
                        for index in range(args.clients):
                            connection = await stack.enter_async_context(
                                connect(
                                    base.replace("http:", "ws:") + "/ws",
                                    origin=base,
                                    max_queue=16,
                                    proxy=None,
                                )
                            )
                            assert json.loads(await connection.recv())["type"] == "status"
                            receivers.append(
                                asyncio.create_task(receive_checked(index, connection))
                            )
                        started_response = await client.post(
                            "/account", json={"session_id": sid, "source": "mock"}
                        )
                        started_response.raise_for_status()
                        sid = started_response.json()["session_id"]
                        cpu_before, _ = process_sample(child.pid)
                        driver_cpu_before = time.process_time()
                        if driver_profile:
                            driver_profile.enable()
                        started = time.perf_counter()
                        workers = [
                            asyncio.create_task(request_worker(i)) for i in range(args.concurrency)
                        ]
                        if churning_peers:
                            workers += [
                                asyncio.create_task(reconnect_worker(i))
                                for i in range(args.reconnectors)
                            ]
                        while time.perf_counter() - started < args.duration:
                            _, rss = process_sample(child.pid)
                            peaks["rss_bytes"] = max(peaks["rss_bytes"], rss)
                            await asyncio.sleep(0.05)
                        stop.set()
                        await asyncio.wait_for(asyncio.gather(*workers), 10)
                        elapsed = time.perf_counter() - started
                        cpu_after, _ = process_sample(child.pid)
                        driver_cpu_after = time.process_time()
                        if driver_profile:
                            driver_profile.disable()
                        if not changing_sessions:
                            async with asyncio.timeout(10):
                                while not (temporary_path / "source-finished.json").exists():
                                    await asyncio.sleep(0.01)
                                generated = json.loads(
                                    (temporary_path / "source-finished.json").read_text()
                                )["generated"]
                                while any(peer["received"] < generated for peer in peer_stats):
                                    if any(task.done() for task in receivers):
                                        break
                                    await asyncio.sleep(0.01)
                        for task in receivers:
                            task.cancel()
                        await asyncio.gather(*receivers, return_exceptions=True)
            finally:
                if driver_profile:
                    driver_profile.disable()
                stop.set()
                for task in workers + receivers:
                    task.cancel()
                await asyncio.gather(*workers, *receivers, return_exceptions=True)
                if child.poll() is None:
                    assert child.stdin is not None
                    try:
                        child.stdin.write("stop\n")
                        child.stdin.flush()
                    except BrokenPipeError:
                        pass
                    try:
                        await asyncio.to_thread(child.wait, timeout=25)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        await asyncio.to_thread(child.wait, timeout=5)
                if child.stdin is not None:
                    child.stdin.close()
            if child.returncode != 0 or not (temporary_path / "server-result.json").exists():
                log.seek(0)
                raise RuntimeError(f"Load server exited {child.returncode}: {log.read()[-2000:]}")
            server_result = json.loads((temporary_path / "server-result.json").read_text())
            reports = {name: metric.report(elapsed) for name, metric in metrics.items()}
            checks = {
                "http": bool(reports) and all(not metric.errors for metric in metrics.values()),
                "handshakes": not handshake.errors
                and (not churning_peers or handshake.statuses[101] > 0),
                "websocket_receivers": not receiver_errors,
                "websocket_order": all(
                    peer["in_order"] and peer["gaps"] == 0 for peer in peer_stats
                ),
                "websocket_delivery": changing_sessions
                or all(peer["received"] == server_result["generated"] for peer in peer_stats),
                "source_active": server_result["generated"] > 0
                and all(peer["received"] > 0 for peer in peer_stats),
                "source_rate": changing_sessions
                or server_result["generated"] >= args.duration * args.comment_rate * 0.95,
                "archive": server_result["integrity"] == "ok"
                and server_result["sqlite_order"]
                and server_result["sqlite_contiguous"]
                and server_result["sqlite_comments"] == server_result["generated"]
                and server_result["storage"]["dropped"] == 0,
                "bounded": peaks["pending_commands"] <= 16 and peaks["websocket_connections"] <= 16,
                "no_feed_drops": server_result["source_drops"]
                == server_result["slow_disconnects"]
                == 0,
                "clean_shutdown": child.returncode == 0 and server_result["clean_shutdown"],
                "workers": server_result["fault"] is None and server_result["recoveries"] == 0,
                "http_latency": all(
                    report["latency_ms"]["p99"] <= args.max_http_p99_ms
                    for report in reports.values()
                ),
            }
            result = {
                "ok": all(checks.values()),
                "checks": checks,
                "mode": args.mode,
                "concurrency": args.concurrency,
                "clients": peer_stats,
                "duration_seconds": round(elapsed, 3),
                "comment_rate": args.comment_rate,
                "comment_size": args.comment_size,
                "http": reports,
                "health_failure_contexts": dict(health_failures),
                "receiver_errors": dict(receiver_errors),
                "http_requests_per_second": round(
                    sum(metric.count for metric in metrics.values()) / elapsed, 2
                ),
                "handshakes": handshake.report(elapsed),
                "peaks": peaks,
                "websocket_latency_ms": {
                    f"p{p}": percentile_ms(list(ws_latencies), p) for p in (50, 95, 99)
                },
                "server_cpu_seconds": round(cpu_after - cpu_before, 3),
                "server_cpu_percent_one_core": round((cpu_after - cpu_before) / elapsed * 100, 2),
                "driver_cpu_percent_one_core": round(
                    (driver_cpu_after - driver_cpu_before) / elapsed * 100, 2
                ),
                "server": server_result,
                "sample_limit": SAMPLES,
                "interpretation": "closed-loop HTTP concurrency; latency includes client/network; "
                "peaks are sampled health observations, hard caps verified by admission tests; "
                "WS latency uses same-host UTC clocks; sample quantiles retain last10000; "
                "mixed-session boundaries intentionally discard queued old-session display events",
            }
            if driver_profile:
                result["driver_profile"] = profile_summary(driver_profile)
                result["driver_profile"]["timer"] = "thread_time_cpu"
                result["driver_profile"]["scope"] = "load generator process during request window"
    result["temporary_directory_removed"] = not temporary_path.exists()
    result["ok"] &= result["temporary_directory_removed"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("read", "mixed", "churn", "mixed-churn"), default="read")
    parser.add_argument("--duration", type=float, default=10)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--clients", type=int, default=2)
    parser.add_argument("--reconnectors", type=int, default=32)
    parser.add_argument("--comment-rate", type=float, default=500)
    parser.add_argument("--comment-size", type=int, default=1000)
    parser.add_argument("--max-http-p99-ms", type=float, default=1000)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--fd", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--state-dir", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error(
            "This localhost process-isolation runner requires Linux /proc and inherited sockets"
        )
    if not all(
        math.isfinite(n) and n > 0 for n in (args.duration, args.comment_rate, args.max_http_p99_ms)
    ):
        parser.error("duration, comment-rate and max-http-p99-ms must be positive and finite")
    if (
        not 1 <= args.concurrency <= 256
        or not 1 <= args.clients <= 16
        or not 1 <= args.reconnectors <= 256
    ):
        parser.error("concurrency/reconnectors must be1..256 and clients1..16")
    if not 1 <= args.comment_size <= 10_000:
        parser.error("comment-size must be1..10000")
    if args.serve:
        if args.fd is None or args.state_dir is None:
            parser.error("Internal server mode needs fd and state-dir")
        with asyncio.Runner(
            loop_factory=uvicorn.Config("app.main:app").get_loop_factory()
        ) as runner:
            runner.run(serve(args))
    else:
        with asyncio.Runner(
            loop_factory=uvicorn.Config("app.main:app").get_loop_factory()
        ) as runner:
            result = runner.run(run_load(args))
        print(json.dumps(result))
        if not result["ok"]:
            parser.exit(1, "API/WS load checks failed; see JSON checks\n")


if __name__ == "__main__":
    main()
