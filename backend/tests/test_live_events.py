import asyncio
from itertools import count

from TikTokLive.events import (
    CommentEvent,
    FollowEvent,
    GiftEvent,
    LikeEvent,
    LiveEndEvent,
    LivePauseEvent,
    LiveUnpauseEvent,
    RoomUserSeqEvent,
    ShareEvent,
    SubNotifyEvent,
)

from app.config import Settings
from app.models import Activity, Comment, LiveInfo, Status
from app.sources.base import SourceSink
from app.sources.mock import MockSource
from app.sources.tiktok import TikTokSource, parse_activity, parse_comment
from app.websocket import WebSocketManager

USER = {"nickname": "시청자", "displayId": "viewer"}


def test_comment_avatar_and_v3_badges_without_legacy_helpers():
    event = CommentEvent.from_dict(
        {
            "content": "안녕하세요",
            "userIdentity": {"isSubscriberOfAnchor": True},
            "user": {
                **USER,
                "avatarThumb": {"urlList": ["javascript:bad", "https://example.com/a.png"]},
                "badgeList": [
                    {"sceneType": 10, "privilegeLogExtra": {"level": "12"}},
                    {"sceneType": 4, "privilegeLogExtra": {"level": "0"}},
                    {"sceneType": 8, "privilegeLogExtra": {"level": "99"}},
                ],
            },
        }
    )
    comment = parse_comment(event)
    assert comment is not None
    assert comment.user.avatar_url == "https://example.com/a.png"
    assert [(b.kind, b.level) for b in comment.user.badges] == [("subscriber", 0), ("fan", 12)]
    event.user.avatar_thumb.url_list = ["https://user:secret@example.com/a", "data:image/png;bad"]
    event.user.badge_list[0].privilege_log_extra.level = "broken"
    result = parse_comment(event)
    assert result.user.avatar_url is None
    assert result.user.badges[1].level is None
    assert result.comment == "안녕하세요"


def test_activity_mapping_and_cumulative_gift_streak():
    data = {"user": USER, "gift": {"name": "장미", "type": 1}, "repeatCount": 5}
    assert parse_activity(GiftEvent.from_dict(data)) is None
    final = parse_activity(GiftEvent.from_dict({**data, "repeatEnd": 1}))
    assert (final.kind, final.gift_name, final.count) == ("gift", "장미", 5)
    assert parse_activity(GiftEvent.from_dict({**data, "gift": {"type": 2}})).count == 5
    for event_type, kind in (
        (FollowEvent, "follow"),
        (ShareEvent, "share"),
        (SubNotifyEvent, "subscribe"),
    ):
        assert parse_activity(event_type.from_dict({"user": USER})).kind == kind
    assert parse_activity(FollowEvent.from_dict({})) is None


async def test_live_snapshot_coalesces_counts_and_resets_at_session_boundary():
    manager = WebSocketManager(Status(source="tiktok", state="connected", message=""))
    sent = []
    manager.broadcast = sent.append
    sink = SourceSink(asyncio.Queue(10), manager)
    source = TikTokSource(sink, Settings(_env_file=None), "test")
    for n in range(500):
        source.on_viewers(RoomUserSeqEvent.from_dict({"total": n}))
        source.on_likes(LikeEvent.from_dict({"total": n * 10}))
    assert not sent  # Latest counts retained without flooding any queue.
    consumer = asyncio.create_task(manager.consume(sink.queue))
    try:
        await asyncio.sleep(1.05)
        assert len(sent) == 1
        assert (sent[0].live.viewers, sent[0].live.likes) == (499, 4990)
        source.on_pause(LivePauseEvent())
        assert sent[-1].live.state == "paused"
        source.on_resume(LiveUnpauseEvent())
        assert sent[-1].live.state == "live"
        source.on_end(LiveEndEvent())
        source.on_disconnect(None)
        assert sent[-1].live.state == "ended"
        manager.begin_session(Status(source="mock", state="connecting", message="new"))
        sink.live(LiveInfo(state="live", viewers=123))
        assert manager.status.live == LiveInfo()
    finally:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)


async def test_mock_cycle_contains_all_events_states_and_offline_avatars():
    manager = WebSocketManager(Status(source="mock", state="connecting", message=""))
    states = []
    original = manager.update_live

    def observe(info):
        states.append(info.state)
        original(info)

    manager.update_live = observe
    queue = asyncio.Queue(100)
    source = MockSource(SourceSink(queue, manager), 0.001, count())
    task = asyncio.create_task(source.run())
    try:
        async with asyncio.timeout(2):
            while len(states) < 24:
                await asyncio.sleep(0.002)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    assert {e.kind for e in events if isinstance(e, Activity)} == {
        "gift",
        "follow",
        "share",
        "subscribe",
    }
    assert (
        states[:24] == ["live"] * 12 + ["paused"] * 2 + ["live"] * 6 + ["ended"] * 2 + ["live"] * 2
    )
    comments = [e for e in events if isinstance(e, Comment)]
    assert all(
        e.user.avatar_url is None or e.user.avatar_url.startswith("/demo-avatar-") for e in comments
    )
    assert any(e.user.badges for e in comments)
