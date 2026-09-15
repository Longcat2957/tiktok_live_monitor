import asyncio
import logging
from contextlib import suppress

import httpx
from TikTokLive import TikTokLiveClient
from TikTokLive.client.errors import TikTokLiveError, UserNotFoundError, UserOfflineError
from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent

from ..config import Settings
from ..models import Comment, SourceState, Status, User
from ..websocket import WebSocketManager, enqueue_comment

logger = logging.getLogger(__name__)


def parse_comment(event: object) -> Comment | None:
    try:
        user = getattr(event, "user", None)
        body = getattr(event, "comment", None)
        nickname = getattr(user, "nickname", "") or ""
        unique_id = getattr(user, "unique_id", "") or ""
        if not isinstance(body, str) or not body.strip():
            raise ValueError("empty comment")
        if not isinstance(nickname, str) or not isinstance(unique_id, str) or user is None:
            raise ValueError("invalid user")
        return Comment(user=User(nickname=nickname, unique_id=unique_id), comment=body)
    except Exception:
        logger.warning("Skipping invalid CommentEvent (payload omitted)")
        return None


class TikTokSource:
    def __init__(
        self, queue: asyncio.Queue[Comment], manager: WebSocketManager, settings: Settings
    ) -> None:
        self.queue = queue
        self.manager = manager
        self.settings = settings
        self.delay = settings.tiktok_reconnect_min_seconds
        self.last_unexpected: type[Exception] | None = None

    def status(self, state: SourceState, message: str) -> None:
        self.manager.set_status(Status(source="tiktok", state=state, message=message))

    def on_comment(self, event: CommentEvent) -> None:
        # Synchronous callback: enqueue before the next event can overtake this one.
        comment = parse_comment(event)
        if comment:
            enqueue_comment(self.queue, comment)

    def on_connect(self, _event: ConnectEvent) -> None:
        self.delay = self.settings.tiktok_reconnect_min_seconds
        self.last_unexpected = None
        self.status("connected", "TikTok LIVE 연결됨")

    def on_disconnect(self, _event: DisconnectEvent) -> None:
        self.status("disconnected", "방송 연결 끊김 · 재연결 대기")

    async def run(self) -> None:
        while True:
            client: TikTokLiveClient | None = None
            connection: asyncio.Task[None] | None = None
            try:
                self.status("connecting", "TikTok LIVE 연결 중")
                client = TikTokLiveClient(unique_id=self.settings.tiktok_username)
                client.add_listener(CommentEvent, self.on_comment)
                client.add_listener(ConnectEvent, self.on_connect)
                client.add_listener(DisconnectEvent, self.on_disconnect)
                # 7.0.1 connect()/close() call run_until_complete during cleanup.
                # start(), disconnect(), and web.close() are async public APIs.
                connection = await client.start(fetch_gift_info=False, fetch_room_info=False)
                await asyncio.shield(connection)
                self.status("waiting", "방송이 종료되었습니다 · 다음 방송 대기")
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
                    logger.exception("Unexpected TikTok adapter failure")
                    self.last_unexpected = type(exc)
                else:
                    logger.warning("Repeated TikTok adapter failure: %s", type(exc).__name__)
                self.status("error", "방송 연결 오류 · 자동 재연결 대기")
            finally:
                if client is not None:
                    with suppress(Exception, asyncio.CancelledError):
                        await asyncio.wait_for(client.disconnect(), timeout=5)
                    if connection is not None and not connection.done():
                        connection.cancel()
                    if connection is not None:
                        await asyncio.gather(connection, return_exceptions=True)
                    with suppress(Exception):
                        await asyncio.wait_for(client.web.close(), timeout=5)
                    client.remove_all_listeners()
            logger.info("TikTok reconnect in %.1fs", self.delay)
            await asyncio.sleep(self.delay)
            self.delay = min(self.delay * 2, self.settings.tiktok_reconnect_max_seconds)
