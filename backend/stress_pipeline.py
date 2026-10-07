"""Sustained SQLite + EventSink + real localhost HTTP/WebSocket check.

Run from backend/: python stress_pipeline.py --duration 60 --rate 100
For a Pi soak use --duration 3600; this does not simulate a physical power cut.
All generated data lives in a temporary directory and is removed after validation.
"""

import argparse
import asyncio
import json
import math
import os
import resource
import socket
import sqlite3
import sys
import threading
from collections import deque
from contextlib import AsyncExitStack, closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
import uvicorn
from websockets.asyncio.client import connect

from app.config import Settings
from app.main import create_app
from app.schemas.events import Comment, User
from app.services.archive import BATCH_SIZE, CAPACITY
from app.services.event_sink import EventSink
from profile_pipeline import percentile_ms

SAMPLE_LIMIT = 10_000
MIN_RATE_RATIO = 0.95


def rss_bytes() -> int:
    if Path("/proc/self/statm").exists():
        return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
        1 if sys.platform == "darwin" else 1024
    )


async def run_soak(
    *,
    duration: float = 60,
    rate: float = 100,
    clients: int = 2,
    comment_size: int = 100,
    max_rss_growth_mib: float = 32,
    max_p99_ms: float | None = None,
    max_latency_ms: float | None = None,
    directory: Path | None = None,
) -> dict[str, object]:
    loop = asyncio.get_running_loop()
    baseline_tasks = asyncio.all_tasks()
    timestamps: list[tuple[int, float] | None] = [None] * SAMPLE_LIMIT
    latencies: deque[int] = deque(maxlen=SAMPLE_LIMIT)
    samples: deque[dict[str, float | int]] = deque(maxlen=120)
    peers = [{"received": 0, "last": -1, "in_order": True} for _ in range(clients)]
    peaks = {"source": 0, "peer": 0, "archive": 0, "rss_bytes": 0}
    source_finished = asyncio.Event()
    sampling_finished = asyncio.Event()
    generated = 0
    source_elapsed = 0.0
    latency_evictions = 0
    max_latency_ns = 0
    sample_count = 0
    warm_rss: int | None = None
    warm_min: int | None = None
    warm_peak = 0

    class Source:
        def __init__(self, sink: EventSink) -> None:
            self.sink = sink

        async def run(self) -> None:
            nonlocal generated, source_elapsed
            self.sink.status("connected", "SQLite soak")
            user = User(nickname="Soak", unique_id="soak")
            body = "x" * comment_size
            started = loop.time()
            while loop.time() < started + duration:
                await asyncio.sleep(max(0, started + generated / rate - loop.time()))
                if loop.time() >= started + duration:
                    break
                timestamps[generated % SAMPLE_LIMIT] = (generated, loop.time())
                self.sink.publish(Comment(id=f"soak-{generated}", user=user, comment=body))
                generated += 1
                peaks["source"] = max(peaks["source"], self.sink.queue.qsize())
                assert self.sink.archive is not None
                peaks["archive"] = max(peaks["archive"], self.sink.archive.get_health().queued)
            source_elapsed = loop.time() - started
            source_finished.set()
            await asyncio.Event().wait()  # Stay alive until the normal monitor stop command.

    async def receive(index: int, connection) -> None:
        nonlocal latency_evictions, max_latency_ns
        async for raw in connection:
            event = json.loads(raw)
            if event["type"] != "comment":
                continue
            sequence = int(event["id"].removeprefix("soak-"))
            peer = peers[index]
            peer["in_order"] &= sequence > peer["last"]
            peer["last"] = sequence
            peer["received"] += 1
            stamp = timestamps[sequence % SAMPLE_LIMIT]
            if stamp is not None and stamp[0] == sequence:
                latency = int((loop.time() - stamp[1]) * 1_000_000_000)
                latencies.append(latency)
                max_latency_ns = max(max_latency_ns, latency)
            else:
                latency_evictions += 1

    temporary_path: Path
    with TemporaryDirectory(prefix="sqlite-soak-", dir=directory) as temporary:
        temporary_path = Path(temporary)
        archive_path = temporary_path / "monitor.sqlite3"
        app = create_app(Settings(_env_file=None, archive_path=archive_path, log_level="WARNING"))
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.setblocking(False)
        port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        server = uvicorn.Server(
            uvicorn.Config(
                app, log_level="error", ws="websockets-sansio", timeout_graceful_shutdown=20
            )
        )
        serving = asyncio.create_task(server.serve(sockets=[listener]), name="soak-server")
        receivers: list[asyncio.Task[None]] = []
        sampler: asyncio.Task[None] | None = None
        started = loop.time()
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if serving.done():
                        await serving
                        raise RuntimeError("Soak server stopped before startup")
                    await asyncio.sleep(0.01)
            monitor = app.state.monitor
            original_broadcast = monitor.broadcaster.broadcast

            def measured_broadcast(event) -> None:
                original_broadcast(event)
                peaks["peer"] = max(
                    peaks["peer"],
                    max(
                        (peer.queue.qsize() for peer in monitor.broadcaster.clients.values()),
                        default=0,
                    ),
                )

            async def sample() -> None:
                nonlocal sample_count, warm_rss, warm_min, warm_peak
                while not sampling_finished.is_set():
                    elapsed = loop.time() - started
                    rss = rss_bytes()
                    sample_count += 1
                    peaks["rss_bytes"] = max(peaks["rss_bytes"], rss)
                    if elapsed >= min(5, duration / 4):
                        warm_rss = rss if warm_rss is None else warm_rss
                        warm_min = rss if warm_min is None else min(warm_min, rss)
                        warm_peak = max(warm_peak, rss)
                    samples.append(
                        {
                            "seconds": round(elapsed, 3),
                            "rss_bytes": rss,
                            "archive_queued": monitor.archive.get_health().queued,
                        }
                    )
                    await asyncio.sleep(min(1, duration / 4))

            sampler = asyncio.create_task(sample(), name="soak-resource-sampler")
            with (
                patch.object(monitor, "_make_stream", new=Source),
                patch.object(monitor.broadcaster, "broadcast", new=measured_broadcast),
            ):
                async with AsyncExitStack() as stack:
                    connections = [
                        await stack.enter_async_context(
                            connect(base.replace("http:", "ws:") + "/ws", origin=base, max_queue=16)
                        )
                        for _ in range(clients)
                    ]
                    initial = [json.loads(await connection.recv()) for connection in connections]
                    assert all(event["type"] == "status" for event in initial)
                    receivers = [
                        asyncio.create_task(receive(index, connection), name=f"soak-client-{index}")
                        for index, connection in enumerate(connections)
                    ]
                    async with httpx.AsyncClient(
                        base_url=base, headers={"Origin": base}, timeout=15
                    ) as client:
                        response = await client.post(
                            "/account",
                            json={"source": "mock", "session_id": initial[0]["session_id"]},
                        )
                        response.raise_for_status()
                        await asyncio.wait_for(source_finished.wait(), duration + 10)
                        await asyncio.wait_for(monitor.queue.join(), 10)
                        async with asyncio.timeout(10):
                            while any(peer["received"] < generated for peer in peers):
                                if any(task.done() for task in receivers):
                                    break
                                await asyncio.sleep(0.01)
                        response = await client.request(
                            "DELETE", "/account", json={"session_id": response.json()["session_id"]}
                        )
                        response.raise_for_status()
                    for task in receivers:
                        task.cancel()
                    await asyncio.gather(*receivers, return_exceptions=True)
        finally:
            sampling_finished.set()
            if sampler is not None:
                sampler.cancel()
                await asyncio.gather(sampler, return_exceptions=True)
            for task in receivers:
                task.cancel()
            await asyncio.gather(*receivers, return_exceptions=True)
            server.should_exit = True
            try:
                await asyncio.wait_for(serving, 25)
            finally:
                listener.close()

        storage = monitor.archive.get_health()
        with closing(sqlite3.connect(archive_path.as_uri() + "?mode=ro", uri=True)) as database:
            integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
            db_comments = 0
            db_in_order = True
            last_id = 0
            for row_id, event_id in database.execute(
                "SELECT id,event_id FROM comments ORDER BY id"
            ):
                db_in_order &= row_id > last_id and event_id == f"soak-{db_comments}"
                last_id = row_id
                db_comments += 1
            db_diagnostics = database.execute("SELECT COUNT(*) FROM diagnostics").fetchone()[0]
        async with asyncio.timeout(5):
            while any(thread.name.startswith("sqlite-archive") for thread in threading.enumerate()):
                await asyncio.sleep(0.01)
        leftovers = [
            task.get_name() for task in asyncio.all_tasks() - baseline_tasks if not task.done()
        ]
        growth = max(0, warm_peak - (warm_min or warm_peak))
        p99_ms = percentile_ms(list(latencies), 99)
        target_count = duration * rate
        checks = {
            "throughput": generated >= max(1, math.floor(target_count * MIN_RATE_RATIO)),
            "integrity": integrity == "ok",
            "archive_accounting": db_comments == generated == storage.saved_comments
            and storage.saved_diagnostics == db_diagnostics,
            "archive_order": db_in_order,
            "no_drops_or_recovery": storage.dropped
            == monitor.broadcaster.dropped_comments
            == monitor.broadcaster.slow_disconnects
            == monitor.recoveries
            == 0
            and storage.error is None,
            "websocket_delivery": all(
                peer["received"] == generated and peer["last"] == generated - 1 and peer["in_order"]
                for peer in peers
            ),
            "bounded_queues": peaks["source"] <= monitor.config.comment_queue_size
            and peaks["peer"] <= monitor.broadcaster.capacity
            and peaks["archive"] <= CAPACITY + BATCH_SIZE,
            "rss_growth": growth <= max_rss_growth_mib * 1024 * 1024,
            "latency": latency_evictions == 0
            and p99_ms is not None
            and (max_p99_ms is None or p99_ms <= max_p99_ms)
            and (max_latency_ms is None or max_latency_ns / 1_000_000 <= max_latency_ms),
            "clean_shutdown": storage.queued == 0
            and not monitor.broadcaster.tasks
            and not monitor.commands
            and monitor.archive._executor is None
            and not leftovers,
        }
        result = {
            "ok": all(checks.values()),
            "checks": checks,
            "duration_seconds": duration,
            "elapsed_seconds": round(loop.time() - started, 3),
            "target_rate_per_sec": rate,
            "source_elapsed_seconds": round(source_elapsed, 3),
            "achieved_rate_per_sec": round(generated / source_elapsed, 3),
            "target_count": target_count,
            "achieved_count_ratio": round(generated / target_count, 4),
            "minimum_count_ratio": MIN_RATE_RATIO,
            "comment_size": comment_size,
            "generated": generated,
            "sqlite_comments": db_comments,
            "sqlite_diagnostics": db_diagnostics,
            "clients": peers,
            "storage": storage.model_dump(),
            "source_drops": monitor.broadcaster.dropped_comments,
            "slow_disconnects": monitor.broadcaster.slow_disconnects,
            "queue_peaks": {key: peaks[key] for key in ("source", "peer", "archive")},
            "latency_ms": {
                f"p{percent}": percentile_ms(list(latencies), percent) for percent in (50, 95, 99)
            },
            "latency_sample_limit": SAMPLE_LIMIT,
            "latency_retained_samples": len(latencies),
            "latency_stamp_evictions": latency_evictions,
            "max_p99_ms": max_p99_ms,
            "max_latency_ms": round(max_latency_ns / 1_000_000, 3),
            "allowed_max_latency_ms": max_latency_ms,
            "rss": {
                "measurement": "current_proc_statm"
                if Path("/proc/self/statm").exists()
                else "peak_rusage",
                "peak_bytes": peaks["rss_bytes"],
                "first_after_warmup_bytes": warm_rss,
                "min_after_warmup_bytes": warm_min,
                "max_after_warmup_bytes": warm_peak,
                "growth_after_warmup_bytes": growth,
                "allowed_growth_mib": max_rss_growth_mib,
                "sample_count": sample_count,
                "last_samples": list(samples),
            },
            "leftover_tasks": leftovers,
        }
    result["temporary_directory_removed"] = not temporary_path.exists()
    result["ok"] = result["ok"] and result["temporary_directory_removed"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--duration", type=float, default=60, help="seconds; use 3600 for a one-hour soak"
    )
    parser.add_argument("--rate", type=float, default=100, help="synthetic comments per second")
    parser.add_argument("--clients", type=int, default=2)
    parser.add_argument(
        "--max-rss-growth-mb",
        type=float,
        default=32,
        help="allowed RSS growth in MiB after up to five seconds of warmup (default: 32)",
    )
    parser.add_argument(
        "--comment-size", type=int, default=100, help="ASCII comment characters (1..10000)"
    )
    parser.add_argument(
        "--max-p99-ms", type=float, help="optional p99 latency budget in milliseconds"
    )
    parser.add_argument(
        "--max-latency-ms",
        type=float,
        help="optional whole-run maximum latency budget in milliseconds",
    )
    parser.add_argument(
        "--directory", type=Path, help="existing directory on the filesystem to test"
    )
    args = parser.parse_args()
    if not all(
        math.isfinite(value) and value > 0
        for value in (args.duration, args.rate, args.max_rss_growth_mb)
    ):
        parser.error("duration, rate and max-rss-growth-mb must be positive and finite")
    if not 1 <= args.clients <= 16:
        parser.error("clients must be between 1 and 16")
    if not 1 <= args.comment_size <= 10_000:
        parser.error("comment-size must be between 1 and 10000")
    if args.max_p99_ms is not None and (not math.isfinite(args.max_p99_ms) or args.max_p99_ms <= 0):
        parser.error("max-p99-ms must be positive and finite")
    if args.max_latency_ms is not None and (
        not math.isfinite(args.max_latency_ms) or args.max_latency_ms <= 0
    ):
        parser.error("max-latency-ms must be positive and finite")
    result = asyncio.run(
        run_soak(
            duration=args.duration,
            rate=args.rate,
            clients=args.clients,
            comment_size=args.comment_size,
            max_rss_growth_mib=args.max_rss_growth_mb,
            max_p99_ms=args.max_p99_ms,
            max_latency_ms=args.max_latency_ms,
            directory=args.directory,
        )
    )
    print(json.dumps(result))
    if not result["ok"]:
        parser.exit(1, "SQLite/WebSocket soak checks failed; see JSON checks\n")


if __name__ == "__main__":
    main()
