import asyncio
from itertools import count
from unittest.mock import AsyncMock, patch

from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    CommentEvent,
    ConnectEvent,
    ControlEvent,
    DisconnectEvent,
    FollowEvent,
    GiftEvent,
    LikeEvent,
    LiveEndEvent,
    LivePauseEvent,
    LiveUnpauseEvent,
    RoomUserSeqEvent,
    ShareEvent,
    SocialEvent,
    SubNotifyEvent,
)
from TikTokLive.proto import (
    ControlAction,
    ProtoMessageFetchResult,
    ProtoMessageFetchResultBaseProtoMessage,
)

from app.config import Settings
from app.integrations.tiktok import TikTokStream, parse_activity, parse_comment
from app.realtime.broadcaster import WebSocketBroadcaster
from app.schemas.events import Activity, Comment, LiveInfo, Status
from app.services.demo import DemoStream
from app.services.event_sink import EventSink

USER = {"nickname": "시청자", "displayId": "viewer"}


async def test_upstream_wire_events_reach_registered_listeners_without_payload_logs():
    manager = WebSocketBroadcaster(Status(source="tiktok", state="connecting", message=""))
    queue = asyncio.Queue(20)
    source = TikTokStream(EventSink(queue, manager), Settings(_env_file=None), "test")
    client = TikTokLiveClient(unique_id="test")
    ready = asyncio.Event()
    connection = asyncio.create_task(asyncio.Event().wait())

    async def start(**kwargs):
        ready.set()
        return connection

    async def deliver(method, event):
        response = ProtoMessageFetchResult(
            messages=[ProtoMessageFetchResultBaseProtoMessage(method=method, payload=bytes(event))]
        )
        async for parsed in client._parse_webcast_response(response):
            client.emit(parsed.get_type(), parsed)

    with (
        patch("app.integrations.tiktok.TikTokLiveClient", return_value=client),
        patch.object(client, "start", side_effect=start),
        patch.object(client, "disconnect", new_callable=AsyncMock),
        patch.object(client.logger, "error") as error_log,
    ):
        task = asyncio.create_task(source.run())
        try:
            await asyncio.wait_for(ready.wait(), 1)
            client.emit(ConnectEvent.get_type(), ConnectEvent(unique_id="test", room_id=1))
            assert manager.status.state == "connected"
            assert manager.status.live.state == "live"
            # Exercise the real upstream parser's failure branch, not app-level validation.
            broken = ProtoMessageFetchResultBaseProtoMessage(
                method="WebcastChatMessage", payload=b"\x0a\xffsecret-payload"
            )
            await client._parse_webcast_response_message(ProtoMessageFetchResult(), broken)
            error_log.assert_not_called()
            await deliver(
                "WebcastChatMessage", CommentEvent.from_dict({"user": USER, "content": "hello"})
            )
            gift = {"user": USER, "gift": {"name": "장미", "type": 1}, "repeatCount": 5}
            await deliver("WebcastGiftMessage", GiftEvent.from_dict(gift))
            await deliver("WebcastGiftMessage", GiftEvent.from_dict({**gift, "repeatEnd": 1}))
            for marker in ("follow", "share"):
                await deliver(
                    "WebcastSocialMessage",
                    SocialEvent.from_dict(
                        {"user": USER, "common": {"displayText": {"key": marker}}}
                    ),
                )
            await deliver("WebcastSubNotifyMessage", SubNotifyEvent.from_dict({"user": USER}))
            await deliver("WebcastRoomUserSeqMessage", RoomUserSeqEvent.from_dict({"total": 123}))
            await deliver("WebcastLikeMessage", LikeEvent.from_dict({"total": 456}))
            for action, state in (
                (ControlAction.STREAM_PAUSED, "paused"),
                (ControlAction.STREAM_UNPAUSED, "live"),
                (ControlAction.STREAM_ENDED, "ended"),
            ):
                await deliver("WebcastControlMessage", ControlEvent(action=action))
                assert manager.status.live.state == state
            assert (manager.status.live.viewers, manager.status.live.likes) == (123, 456)
            client.emit(DisconnectEvent.get_type(), DisconnectEvent())
            assert manager.status.state == "disconnected"
            assert manager.status.live.state == "ended"
            feed = [queue.get_nowait() for _ in range(queue.qsize())]
            assert [getattr(item, "kind", item.type) for item in feed] == [
                "comment",
                "gift",
                "follow",
                "share",
                "subscribe",
            ]
            assert all(item.user.unique_id == "viewer" for item in feed)
            assert feed[1].count == 5
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            connection.cancel()
            await asyncio.gather(connection, return_exceptions=True)


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
    manager = WebSocketBroadcaster(Status(source="tiktok", state="connected", message=""))
    sent = []
    manager.broadcast = sent.append
    sink = EventSink(asyncio.Queue(10), manager)
    source = TikTokStream(sink, Settings(_env_file=None), "test")
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
    manager = WebSocketBroadcaster(Status(source="mock", state="connecting", message=""))
    states = []
    original = manager.update_live

    def observe(info):
        states.append(info.state)
        original(info)

    manager.update_live = observe
    queue = asyncio.Queue(100)
    source = DemoStream(EventSink(queue, manager), 0.001, count())
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
