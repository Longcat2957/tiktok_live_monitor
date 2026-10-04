"""Measure the in-process event pipeline without TikTok or a browser.

Run from backend/: python profile_pipeline.py [--profile]
"""

import argparse
import asyncio
import cProfile
import json
import math
import pstats
import tracemalloc
from pathlib import Path
from time import perf_counter, perf_counter_ns, process_time
from typing import Any, cast

from fastapi import WebSocket

from app.realtime.broadcaster import Peer, WebSocketBroadcaster
from app.schemas.events import Comment, FeedEvent, Message, Status, User
from app.services.event_sink import EventSink


class ProfilingSocket:
    def __init__(self, sent_at: list[int], latencies: list[int], delay_ms: float) -> None:
        self.sent_at = sent_at
        self.latencies = latencies
        self.delay_ms = delay_ms
        self.received = 0
        self.first: int | None = None
        self.last: int | None = None
        self.in_order = True
        self.serialized_chars = 0

    async def accept(self) -> None:
        pass

    async def send_json(self, value: dict[str, Any]) -> None:
        if self.delay_ms:
            await asyncio.sleep(self.delay_ms / 1000)
        self.serialized_chars += len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        if value["type"] == "comment":
            sequence = int(value["id"])
            self.latencies.append(perf_counter_ns() - self.sent_at[sequence])
            self.in_order &= self.last is None or sequence > self.last
            self.first = sequence if self.first is None else self.first
            self.last = sequence
            self.received += 1

    async def close(self, code: int) -> None:
        pass


class ProfilingBroadcaster(WebSocketBroadcaster):
    def __init__(self, clients: int, peer_capacity: int) -> None:
        super().__init__(
            Status(source="mock", state="connected", message="profile"),
            capacity=peer_capacity,
            max_clients=clients,
        )
        self.peer_queue_peak = 0

    def broadcast(self, message: Message) -> None:
        super().broadcast(message)
        self.peer_queue_peak = max(
            self.peer_queue_peak,
            max((peer.queue.qsize() for peer in self.clients.values()), default=0),
        )


def percentile_ms(latencies: list[int], percent: int) -> float | None:
    if not latencies:
        return None
    ordered = sorted(latencies)
    return round(ordered[(len(ordered) * percent + 99) // 100 - 1] / 1_000_000, 3)


async def drain_sender(peer: Peer) -> None:
    joined = asyncio.create_task(peer.queue.join())
    try:
        await asyncio.wait((joined, peer.task), return_when=asyncio.FIRST_COMPLETED)
    finally:
        joined.cancel()
        await asyncio.gather(joined, return_exceptions=True)


async def run_profile(
    *,
    events: int = 5000,
    rate: float = 500,
    clients: int = 2,
    source_capacity: int = 500,
    peer_capacity: int = 100,
    slow_client_ms: float = 0,
) -> dict[str, object]:
    queue: asyncio.Queue[FeedEvent] = asyncio.Queue(source_capacity)
    broadcaster = ProfilingBroadcaster(clients, peer_capacity)
    sink = EventSink(queue, broadcaster)
    sent_at: list[int] = []
    latencies: list[int] = []
    sockets = [
        ProfilingSocket(sent_at, latencies, slow_client_ms if i == clients - 1 else 0)
        for i in range(clients)
    ]
    for socket in sockets:
        await broadcaster.connect(cast(WebSocket, socket))

    consumer = asyncio.create_task(broadcaster.consume(queue))
    source_queue_peak = 0
    started = perf_counter()
    user = User(nickname="Profiler", unique_id="profile")
    try:
        for sequence in range(events):
            await asyncio.sleep(max(0, started + sequence / rate - perf_counter()))
            event = Comment(id=str(sequence), user=user, comment="Synthetic comment")
            sent_at.append(perf_counter_ns())
            sink.publish(event)
            source_queue_peak = max(source_queue_peak, queue.qsize())
        await queue.join()
        drain_timed_out = False
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *(drain_sender(peer) for peer in list(broadcaster.clients.values()))
                ),
                timeout=10,
            )
        except TimeoutError:
            drain_timed_out = True
        elapsed = perf_counter() - started
        source_events = events - broadcaster.dropped_comments
        deliveries = sum(socket.received for socket in sockets)
        return {
            "events": events,
            "target_rate_per_sec": rate,
            "elapsed_seconds": round(elapsed, 3),
            "source_events_per_sec": round(source_events / elapsed, 1),
            "browser_deliveries_per_sec": round(deliveries / elapsed, 1),
            "source_queue_peak": source_queue_peak,
            "peer_queue_peak": broadcaster.peer_queue_peak,
            "source_drops": broadcaster.dropped_comments,
            "slow_disconnects": broadcaster.slow_disconnects,
            "drain_timed_out": drain_timed_out,
            "latency_ms": {
                "p50": percentile_ms(latencies, 50),
                "p95": percentile_ms(latencies, 95),
                "p99": percentile_ms(latencies, 99),
            },
            "clients": [
                {
                    "received": socket.received,
                    "first_sequence": socket.first,
                    "last_sequence": socket.last,
                    "in_order": socket.in_order if socket.received else None,
                    "connected_at_end": cast(WebSocket, socket) in broadcaster.clients,
                    "serialized_chars": socket.serialized_chars,
                }
                for socket in sockets
            ],
        }
    finally:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
        await broadcaster.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=5000)
    parser.add_argument("--rate", type=float, default=500, help="target source events/second")
    parser.add_argument("--clients", type=int, default=2)
    parser.add_argument("--source-capacity", type=int, default=500)
    parser.add_argument("--peer-capacity", type=int, default=100)
    parser.add_argument("--slow-client-ms", type=float, default=0, help="delay the final client")
    parser.add_argument(
        "--profile", action="store_true", help="include CPU and Python heap profile"
    )
    args = parser.parse_args()
    if min(args.events, args.clients, args.source_capacity, args.peer_capacity) <= 0:
        parser.error("events, clients, and capacities must be positive")
    if args.events > 100_000:
        parser.error("events must be at most 100000")
    if args.clients > 16:
        parser.error("clients must be at most 16")
    if args.rate <= 0 or not math.isfinite(args.rate):
        parser.error("rate must be positive and finite")
    if args.slow_client_ms < 0 or not math.isfinite(args.slow_client_ms):
        parser.error("slow-client-ms must be nonnegative")

    profiler = cProfile.Profile(timer=process_time) if args.profile else None
    if profiler:
        tracemalloc.start()
        profiler.enable()
    result = asyncio.run(
        run_profile(
            events=args.events,
            rate=args.rate,
            clients=args.clients,
            source_capacity=args.source_capacity,
            peer_capacity=args.peer_capacity,
            slow_client_ms=args.slow_client_ms,
        )
    )
    if profiler:
        profiler.disable()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        stats = cast(
            dict[tuple[str, int, str], tuple[int, int, float, float, object]],
            getattr(pstats.Stats(profiler), "stats"),
        )
        result["profile"] = {
            "python_heap_peak_bytes": peak,
            "cpu_top": [
                {
                    "file": Path(filename).name,
                    "line": line,
                    "function": name,
                    "calls": values[1],
                    "self_seconds": round(values[2], 6),
                }
                for (filename, line, name), values in sorted(
                    stats.items(), key=lambda item: item[1][2], reverse=True
                )[:10]
            ],
        }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
