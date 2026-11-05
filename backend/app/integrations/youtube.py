import asyncio
import logging
from datetime import UTC, datetime
from urllib.parse import urlsplit

import grpc
import httpx

from ..config import Settings
from ..diagnostics import exception_location
from ..schemas.events import Comment, LiveInfo, User
from ..services.event_sink import EventSink
from .youtube_proto import stream_list_pb2 as proto
from .youtube_proto.stream_list_pb2_grpc import V3DataLiveChatMessageServiceStub

logger = logging.getLogger(__name__)
RETRY_MIN_SECONDS = 2.0
RETRY_MAX_SECONDS = 30.0
VIDEO_WAIT_SECONDS = 30.0
METRICS_INTERVAL_SECONDS = 30.0
CONNECT_TIMEOUT_SECONDS = 15.0
SEEN_LIMIT = 2048


class YouTubeUnavailable(Exception):
    def __init__(self, message: str, *, ended: bool = False) -> None:
        self.message = message
        self.ended = ended


def parse_count(value: object) -> int | None:
    if isinstance(value, str):
        if not value.isascii() or not value.isdecimal() or len(value) > 16:
            return None
        value = int(value)
    return value if type(value) is int and 0 <= value <= 9_007_199_254_740_991 else None


def parse_live(video: dict[str, object]) -> LiveInfo:
    details = video.get("liveStreamingDetails")
    statistics = video.get("statistics")
    ended = isinstance(details, dict) and bool(details.get("actualEndTime"))
    return LiveInfo(
        state="ended" if ended else "live",
        viewers=(
            parse_count(details.get("concurrentViewers"))
            if isinstance(details, dict) and not ended
            else None
        ),
        likes=parse_count(statistics.get("likeCount")) if isinstance(statistics, dict) else None,
    )


def parse_comment(message: proto.LiveChatMessage) -> Comment:
    body = message.snippet.text_message_details.message_text
    if not body.strip() or not message.author_details.channel_id:
        raise ValueError("Invalid YouTube comment")
    avatar = message.author_details.profile_image_url
    try:
        url = urlsplit(avatar)
        if (
            len(avatar) > 2048
            or url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
        ):
            avatar = ""
    except ValueError:
        avatar = ""
    return Comment(
        platform="youtube",
        user=User(
            nickname=message.author_details.display_name,
            unique_id=message.author_details.channel_id,
            avatar_url=avatar or None,
        ),
        comment=body,
    )


class YouTubeStream:
    def __init__(self, sink: EventSink, config: Settings, video_id: str) -> None:
        self.sink = sink
        self.config = config
        self.video_id = video_id
        self.seen: dict[str, None] = {}
        self.page_token = ""
        self.chat_id = ""
        self.delay = RETRY_MIN_SECONDS
        self.live_info = LiveInfo()

    async def _video(self, client: httpx.AsyncClient) -> dict[str, object]:
        response = await client.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "liveStreamingDetails,statistics", "id": self.video_id},
        )
        if response.status_code in (400, 401, 403):
            raise YouTubeUnavailable("YouTube API 키·접근 권한·할당량을 확인해주세요")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("Invalid YouTube video response")
        items = payload["items"]
        if not items:
            raise YouTubeUnavailable("YouTube 방송을 찾을 수 없습니다 · 주소를 확인해주세요")
        if not isinstance(items[0], dict):
            raise ValueError("Invalid YouTube video")
        return items[0]

    async def _chat_id(self, client: httpx.AsyncClient) -> str | None:
        video = await self._video(client)
        details = video.get("liveStreamingDetails")
        if not isinstance(details, dict):
            raise YouTubeUnavailable("실시간 YouTube 방송 주소를 입력해주세요")
        if details.get("actualEndTime"):
            raise YouTubeUnavailable("YouTube 방송이 종료되었습니다", ended=True)
        chat_id = details.get("activeLiveChatId")
        if isinstance(chat_id, str) and 0 < len(chat_id) <= 2048:
            self.live_info = parse_live(video)
            return chat_id
        if details.get("actualStartTime"):
            raise YouTubeUnavailable("YouTube 실시간 채팅이 비활성화되어 있습니다")
        self.sink.status("waiting", "YouTube 방송 시작 대기 중")
        return None

    async def _refresh_metrics(self, client: httpx.AsyncClient) -> None:
        while True:
            await asyncio.sleep(METRICS_INTERVAL_SECONDS)
            try:
                self.live_info = parse_live(await self._video(client))
            except (YouTubeUnavailable, httpx.HTTPError, OSError, ValueError, TimeoutError) as exc:
                self.live_info = LiveInfo(state="live")
                self.sink.diagnostic(
                    "youtube_metrics_failed",
                    level="warning",
                    details={"error_type": type(exc).__name__, "location": exception_location(exc)},
                )
            self.sink.live(self.live_info)

    def _accept(self, response: proto.LiveChatMessageListResponse, since: datetime) -> None:
        self.sink.upstream_message()
        if len(response.next_page_token) > 8192:
            raise ValueError("Invalid YouTube continuation token")
        self.page_token = response.next_page_token
        for message in response.items:
            if message.snippet.type == proto.LiveChatMessageSnippet.TypeWrapper.CHAT_ENDED_EVENT:
                raise YouTubeUnavailable("YouTube 방송이 종료되었습니다", ended=True)
            if message.snippet.type != proto.LiveChatMessageSnippet.TypeWrapper.TEXT_MESSAGE_EVENT:
                continue
            try:
                if not message.id or len(message.id) > 512:
                    raise ValueError("Invalid YouTube message ID")
                published = datetime.fromisoformat(message.snippet.published_at)
                if published.tzinfo is None:
                    raise ValueError("Missing YouTube timestamp timezone")
                # Initial history and reconnect backlogs are never replayed into the live feed.
                if published < since or message.id in self.seen:
                    continue
                comment = parse_comment(message)
            except (ValueError, OverflowError) as exc:
                self.sink.invalid_event("comment", exc)
                continue
            self.seen[message.id] = None
            if len(self.seen) > SEEN_LIMIT:
                self.seen.pop(next(iter(self.seen)))
            self.sink.publish(comment)
        if response.offline_at:
            raise YouTubeUnavailable("YouTube 방송이 종료되었습니다", ended=True)

    async def _receive(self, chat_id: str, key: str, client: httpx.AsyncClient) -> None:
        if self.chat_id != chat_id:
            self.chat_id = chat_id
            self.page_token = ""
            self.seen.clear()
        since = datetime.now(UTC)
        async with grpc.aio.secure_channel(
            "youtube.googleapis.com:443", grpc.ssl_channel_credentials()
        ) as channel:
            await asyncio.wait_for(channel.channel_ready(), timeout=CONNECT_TIMEOUT_SECONDS)
            stub = V3DataLiveChatMessageServiceStub(channel)  # type: ignore[no-untyped-call]
            call = stub.StreamList(
                proto.LiveChatMessageListRequest(
                    live_chat_id=chat_id,
                    part=["id", "snippet", "authorDetails"],
                    page_token=self.page_token,
                ),
                metadata=(("x-goog-api-key", key),),
            )
            metrics: asyncio.Task[None] | None = None
            try:
                response = await call.read()
                if response is grpc.aio.EOF:
                    raise ConnectionError("YouTube stream closed")
                self.delay = RETRY_MIN_SECONDS
                self.sink.live(self.live_info)
                self.sink.status("connected", "YouTube LIVE 연결됨")
                metrics = asyncio.create_task(self._refresh_metrics(client), name="youtube-metrics")
                while response is not grpc.aio.EOF:
                    self._accept(response, since)
                    response = await call.read()
            finally:
                call.cancel()
                if metrics is not None:
                    metrics.cancel()
                    await asyncio.gather(metrics, return_exceptions=True)

    async def run(self) -> None:
        key = self.config.youtube_api_key.get_secret_value().strip()
        if not key:
            self.sink.status("error", "서버에 YOUTUBE_API_KEY를 설정해주세요")
            await asyncio.Event().wait()
        async with httpx.AsyncClient(
            headers={"X-Goog-Api-Key": key}, timeout=15, follow_redirects=False
        ) as client:
            while True:
                try:
                    self.sink.status("connecting", "YouTube LIVE 연결 중")
                    chat_id = await self._chat_id(client)
                    if chat_id is None:
                        await asyncio.sleep(VIDEO_WAIT_SECONDS)
                        continue
                    await self._receive(chat_id, key, client)
                    self.sink.live(LiveInfo())
                    self.sink.status("disconnected", "YouTube 연결 종료 · 재연결 대기")
                except asyncio.CancelledError:
                    raise
                except YouTubeUnavailable as exc:
                    self.sink.live(LiveInfo(state="ended" if exc.ended else "unknown"))
                    self.sink.status("waiting" if exc.ended else "error", exc.message)
                    await asyncio.Event().wait()
                except grpc.aio.AioRpcError as exc:
                    code = exc.code()
                    if code in {
                        grpc.StatusCode.UNAUTHENTICATED,
                        grpc.StatusCode.PERMISSION_DENIED,
                        grpc.StatusCode.INVALID_ARGUMENT,
                        grpc.StatusCode.NOT_FOUND,
                        grpc.StatusCode.FAILED_PRECONDITION,
                    }:
                        ended = False
                        message = "YouTube 채팅·API 권한·할당량을 확인해주세요"
                        if code == grpc.StatusCode.FAILED_PRECONDITION:
                            # gRPC uses the same error for ended and disabled chats.
                            message = (
                                "YouTube 방송이 종료되었거나 실시간 채팅이 비활성화되어 있습니다"
                            )
                            try:
                                video = await self._video(client)
                                ended = parse_live(video).state == "ended"
                                details = video.get("liveStreamingDetails")
                                if ended:
                                    message = "YouTube 방송이 종료되었습니다"
                                elif (
                                    isinstance(details, dict)
                                    and details.get("actualStartTime")
                                    and not details.get("activeLiveChatId")
                                ):
                                    message = "YouTube 실시간 채팅이 비활성화되어 있습니다"
                            except (
                                YouTubeUnavailable,
                                httpx.HTTPError,
                                OSError,
                                ValueError,
                                TimeoutError,
                            ):
                                pass
                        self.sink.live(LiveInfo(state="ended" if ended else "unknown"))
                        self.sink.status("waiting" if ended else "error", message)
                        await asyncio.Event().wait()
                    self._retry_status(exc)
                except (httpx.HTTPError, OSError, ValueError, TimeoutError) as exc:
                    self._retry_status(exc)
                await asyncio.sleep(self.delay)
                self.delay = min(self.delay * 2, RETRY_MAX_SECONDS)

    def _retry_status(self, error: Exception) -> None:
        logger.warning("YouTube connection failed: %s", type(error).__name__)
        self.sink.diagnostic(
            "youtube_connection_failed",
            level="warning",
            details={"error_type": type(error).__name__, "location": exception_location(error)},
        )
        self.sink.live(LiveInfo())
        self.sink.status("error", "YouTube 연결 실패 · 자동 재연결 대기")
