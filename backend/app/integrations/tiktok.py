import asyncio
import logging
from contextlib import suppress
from typing import Literal
from urllib.parse import urlsplit

import httpx
from TikTokLive import TikTokLiveClient
from TikTokLive.client.errors import TikTokLiveError, UserNotFoundError, UserOfflineError
from TikTokLive.events import (
    CommentEvent,
    ConnectEvent,
    DisconnectEvent,
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

from ..config import Settings
from ..schemas.events import Activity, Badge, Comment, LiveInfo, LiveState, SourceState, User
from ..services.event_sink import EventSink

logger = logging.getLogger(__name__)


def avatar_url(user: object) -> str | None:
    image = getattr(user, "avatar_thumb", None)
    for value in (getattr(image, "url_list", None) or [])[:5]:
        if not isinstance(value, str) or len(value) > 2048:
            continue
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme == "https"
                and parsed.hostname
                and not parsed.username
                and not parsed.password
            ):
                return value
        except ValueError:
            continue
    return None


def parse_user(event: object) -> User:
    user = getattr(event, "user", None)
    if user is None:
        raise ValueError("missing user")
    badges: dict[str, Badge] = {}
    identity = getattr(event, "user_identity", None)
    if getattr(identity, "is_subscriber_of_anchor", False) is True:
        badges["subscriber"] = Badge(kind="subscriber")
    # v7's legacy badge helpers reference old fields; read the installed v3 schema.
    for raw in (getattr(user, "badge_list", None) or [])[:32]:
        scene = getattr(raw, "scene_type", None)
        if scene not in (4, 7, 10):  # SUBSCRIBER, NEW_SUBSCRIBER, FANS
            continue
        kind: Literal["fan", "subscriber"] = "fan" if scene == 10 else "subscriber"
        level = getattr(getattr(raw, "privilege_log_extra", None), "level", "")
        parsed_level = None
        if isinstance(level, str) and level.isascii() and level.isdecimal() and len(level) <= 5:
            if int(level) <= 10000:
                parsed_level = int(level)
        badge = Badge(kind=kind, level=parsed_level)
        if kind not in badges or parsed_level is not None:
            badges[kind] = badge
    return User(
        nickname=getattr(user, "nickname", "") or "",
        unique_id=getattr(user, "unique_id", "") or "",
        avatar_url=avatar_url(user),
        badges=list(badges.values()),
    )


def parse_comment(event: object) -> Comment | None:
    try:
        body = getattr(event, "comment", None)
        if not isinstance(body, str) or not body.strip():
            raise ValueError("empty comment")
        return Comment(user=parse_user(event), comment=body)
    except Exception:
        logger.warning("Skipping invalid CommentEvent (payload omitted)")
        return None


def parse_activity(event: object) -> Activity | None:
    try:
        if isinstance(event, GiftEvent):
            gift = event.gift
            # Streak updates contain cumulative counts: show only the final event.
            if gift is not None and gift.type == 1 and not event.repeat_end:
                return None
            return Activity(
                kind="gift",
                user=parse_user(event),
                gift_name=(gift.name if gift else "") or "선물",
                count=max(1, event.repeat_count),
            )
        if isinstance(event, FollowEvent):
            return Activity(kind="follow", user=parse_user(event))
        if isinstance(event, ShareEvent):
            return Activity(kind="share", user=parse_user(event))
        if isinstance(event, SubNotifyEvent):
            return Activity(kind="subscribe", user=parse_user(event))
    except Exception:
        logger.warning("Skipping invalid activity (payload omitted)")
    return None


class TikTokStream:
    def __init__(
        self,
        sink: EventSink,
        settings: Settings,
        username: str,
    ) -> None:
        self.sink = sink
        self.settings = settings
        self.username = username
        self.live_info = LiveInfo()
        self.delay = settings.tiktok_reconnect_min_seconds
        self.last_unexpected: type[Exception] | None = None

    def status(self, state: SourceState, message: str) -> None:
        self.sink.status(state, message)

    def on_comment(self, event: CommentEvent) -> None:
        # Synchronous callback: enqueue before the next event can overtake this one.
        comment = parse_comment(event)
        if comment:
            self.sink.publish(comment)

    def on_activity(self, event: object) -> None:
        activity = parse_activity(event)
        if activity:
            self.sink.publish(activity)

    def on_viewers(self, event: RoomUserSeqEvent) -> None:
        if type(event.total) is int and 0 <= event.total <= 9_007_199_254_740_991:
            self.live_info = self.live_info.model_copy(update={"viewers": event.total})
            self.sink.live(self.live_info)

    def on_likes(self, event: LikeEvent) -> None:
        if type(event.total) is int and 0 <= event.total <= 9_007_199_254_740_991:
            self.live_info = self.live_info.model_copy(update={"likes": event.total})
            self.sink.live(self.live_info)

    def broadcast_state(self, state: LiveState) -> None:
        self.live_info = self.live_info.model_copy(update={"state": state})
        self.sink.live(self.live_info)

    def on_pause(self, _event: LivePauseEvent) -> None:
        self.broadcast_state("paused")

    def on_resume(self, _event: LiveUnpauseEvent) -> None:
        self.broadcast_state("live")

    def on_end(self, _event: LiveEndEvent) -> None:
        self.broadcast_state("ended")

    def on_connect(self, _event: ConnectEvent) -> None:
        self.delay = self.settings.tiktok_reconnect_min_seconds
        self.last_unexpected = None
        self.live_info = LiveInfo(state="live")
        self.sink.live(self.live_info)
        self.status("connected", "TikTok LIVE 연결됨")

    def on_disconnect(self, _event: DisconnectEvent) -> None:
        if self.live_info.state != "ended":
            self.broadcast_state("unknown")
        self.status("disconnected", "방송 연결 끊김 · 재연결 대기")

    async def run(self) -> None:
        while True:
            client: TikTokLiveClient | None = None
            connection: asyncio.Task[None] | None = None
            try:
                self.status("connecting", "TikTok LIVE 연결 중")
                client = TikTokLiveClient(unique_id=self.username)
                # Upstream parse errors otherwise log raw payload bytes and traceback.
                client.ignore_broken_payload = True
                client.add_listener(CommentEvent, self.on_comment)
                client.add_listener(ConnectEvent, self.on_connect)
                client.add_listener(DisconnectEvent, self.on_disconnect)
                client.add_listener(RoomUserSeqEvent, self.on_viewers)
                client.add_listener(LikeEvent, self.on_likes)
                client.add_listener(LivePauseEvent, self.on_pause)
                client.add_listener(LiveUnpauseEvent, self.on_resume)
                client.add_listener(LiveEndEvent, self.on_end)
                for event_type in (GiftEvent, FollowEvent, ShareEvent, SubNotifyEvent):
                    client.add_listener(event_type, self.on_activity)
                # 7.0.1 connect()/close() call run_until_complete during cleanup.
                # start(), disconnect(), and web.close() are async public APIs.
                # Joining may include older comments; only handle the live stream.
                async with asyncio.timeout(30):
                    connection = await client.start(
                        fetch_gift_info=False, fetch_room_info=False, process_connect_events=False
                    )
                await asyncio.shield(connection)
                self.status("waiting", "방송 연결 종료 · 재연결 대기")
            except asyncio.CancelledError:
                raise
            except UserOfflineError:
                self.status("waiting", "방송 시작 대기 중")
            except UserNotFoundError:
                self.status("error", "계정을 찾을 수 없습니다 · 아이디 확인 필요")
            except (TikTokLiveError, httpx.HTTPError, OSError) as exc:
                logger.warning("TikTok connection failed: %s", type(exc).__name__)
                self.status("error", "TikTok 연결 실패 · 네트워크 또는 서비스 확인")
            except Exception as exc:
                if self.last_unexpected is not type(exc):
                    logger.error("Unexpected TikTok adapter failure: %s", type(exc).__name__)
                    self.last_unexpected = type(exc)
                else:
                    logger.warning("Repeated TikTok adapter failure: %s", type(exc).__name__)
                self.status("error", "방송 연결 오류 · 자동 재연결 대기")
            finally:
                if client is not None:
                    try:
                        with suppress(Exception):
                            async with asyncio.timeout(5):
                                await client.disconnect()
                    finally:
                        if connection is not None:
                            connection.cancel()
                        try:
                            if connection is not None:
                                with suppress(Exception, asyncio.CancelledError):
                                    # Only suppress the child's cancellation, not our own.
                                    await asyncio.shield(connection)
                        finally:
                            try:
                                with suppress(Exception):
                                    async with asyncio.timeout(5):
                                        await client.web.close()
                            finally:
                                client.remove_all_listeners()
            # Some upstream cleanup methods may consume cancellation themselves.
            if (task := asyncio.current_task()) is not None and task.cancelling():
                raise asyncio.CancelledError
            logger.info("TikTok reconnect in %.1fs", self.delay)
            await asyncio.sleep(self.delay)
            self.delay = min(self.delay * 2, self.settings.tiktok_reconnect_max_seconds)
