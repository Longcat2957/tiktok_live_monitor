import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import grpc
import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.integrations import youtube
from app.integrations.youtube import YouTubeStream, YouTubeUnavailable, parse_comment, parse_live
from app.integrations.youtube_proto import stream_list_pb2 as proto
from app.integrations.youtube_proto import stream_list_pb2_grpc as rpc
from app.realtime.broadcaster import WebSocketBroadcaster
from app.schemas.events import Status, YouTubeStatus
from app.services.event_sink import EventSink


def message(identity="chat-1", text="안녕하세요 👋", published=None, **kwargs):
    return proto.LiveChatMessage(
        id=identity,
        snippet=proto.LiveChatMessageSnippet(
            type=proto.LiveChatMessageSnippet.TypeWrapper.TEXT_MESSAGE_EVENT,
            published_at=(published or datetime.now(UTC)).isoformat(),
            text_message_details=proto.LiveChatTextMessageDetails(message_text=text),
        ),
        author_details=proto.LiveChatMessageAuthorDetails(
            channel_id="UC-channel", display_name="시청자", **kwargs
        ),
    )


@pytest.fixture
def pipeline():
    broadcaster = WebSocketBroadcaster(
        Status(
            source="tiktok",
            state="connected",
            message="TikTok connected",
            youtube=YouTubeStatus(video_id="abcdefghijk", state="connecting", message="test"),
        )
    )
    queue = asyncio.Queue(3000)
    stream = YouTubeStream(
        EventSink(queue, broadcaster, platform="youtube"),
        Settings(_env_file=None, youtube_api_key=SecretStr("test-secret")),
        "abcdefghijk",
    )
    return stream, queue, broadcaster


def install_http(monkeypatch, handler):
    client_class = httpx.AsyncClient
    clients = []

    def client(**kwargs):
        instance = client_class(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(instance)
        return instance

    monkeypatch.setattr(youtube.httpx, "AsyncClient", client)
    return clients


def live_video(request):
    assert request.url.path == "/youtube/v3/videos"
    assert request.url.params["id"] == "abcdefghijk"
    assert request.url.params["part"] == "liveStreamingDetails,statistics"
    assert request.headers["x-goog-api-key"] == "test-secret"
    assert "key" not in request.url.params
    return httpx.Response(
        200,
        json={
            "items": [
                {
                    "liveStreamingDetails": {
                        "activeLiveChatId": "chat",
                        "concurrentViewers": "123",
                    },
                    "statistics": {"likeCount": "456"},
                }
            ]
        },
    )


async def wait_for_status(broadcaster, state):
    async with asyncio.timeout(2):
        while broadcaster.status.youtube.state != state:
            await asyncio.sleep(0.001)


async def cancel(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_comment_plain_text_and_optional_avatar():
    parsed = parse_comment(
        message(
            text=" <script>alert(1)</script>\n💚 ", profile_image_url="https://yt3.ggpht.com/avatar"
        )
    )
    assert parsed.comment == " <script>alert(1)</script>\n💚 "
    assert parsed.platform == "youtube"
    assert parsed.user.unique_id == "UC-channel"
    assert parsed.user.badges == []
    assert parsed.user.avatar_url == "https://yt3.ggpht.com/avatar"
    assert parse_comment(message(profile_image_url="javascript:alert(1)")).user.avatar_url is None
    assert (
        parse_comment(
            message(profile_image_url="https://user:password@example.com/a")
        ).user.avatar_url
        is None
    )
    with pytest.raises(ValueError):
        parse_comment(message(text=" "))


def test_history_duplicates_invalid_messages_and_receive_order(pipeline):
    stream, queue, _ = pipeline
    since = datetime.now(UTC)
    old = message("old", published=since - timedelta(seconds=1))
    one = message("one", "first", since)
    two = message("two", "second", since + timedelta(seconds=1))
    malformed = message("bad", published=since)
    malformed.snippet.published_at = "invalid"
    activity = message("paid", published=since)
    activity.snippet.type = proto.LiveChatMessageSnippet.TypeWrapper.SUPER_CHAT_EVENT
    stream._accept(
        proto.LiveChatMessageListResponse(
            items=[old, one, one, malformed, activity, two], next_page_token="page-2"
        ),
        since,
    )
    first, second = queue.get_nowait(), queue.get_nowait()
    assert [first.comment, second.comment] == ["first", "second"]
    assert first.id != "one" and first.id != second.id
    assert queue.empty()
    assert stream.page_token == "page-2"
    assert stream.sink.invalid_comments == 1
    assert stream.sink.upstream_messages == 1
    # The same continuation can contain backlog when a connection is resumed.
    stream._accept(
        proto.LiveChatMessageListResponse(items=[two, message("backlog", published=since)]),
        since + timedelta(seconds=2),
    )
    assert queue.empty()


def test_duplicate_memory_is_bounded(pipeline):
    stream, queue, _ = pipeline
    since = datetime.now(UTC)
    stream._accept(
        proto.LiveChatMessageListResponse(
            items=[message(str(i), published=since) for i in range(youtube.SEEN_LIMIT + 10)]
        ),
        since,
    )
    assert len(stream.seen) == youtube.SEEN_LIMIT
    assert queue.qsize() == youtube.SEEN_LIMIT + 10


@pytest.mark.parametrize("ended_event", [False, True])
def test_broadcast_end_is_terminal(pipeline, ended_event):
    stream, queue, _ = pipeline
    since = datetime.now(UTC)
    response = proto.LiveChatMessageListResponse(items=[message("last", published=since)])
    if ended_event:
        response.items.append(
            proto.LiveChatMessage(
                snippet=proto.LiveChatMessageSnippet(
                    type=proto.LiveChatMessageSnippet.TypeWrapper.CHAT_ENDED_EVENT
                )
            )
        )
    else:
        response.offline_at = since.isoformat()
    with pytest.raises(YouTubeUnavailable) as error:
        stream._accept(response, since)
    assert error.value.ended
    assert queue.qsize() == 1


async def test_real_grpc_wire_and_cancellation(pipeline, monkeypatch):
    stream, queue, broadcaster = pipeline
    clients = install_http(monkeypatch, live_video)
    cancelled = asyncio.Event()
    requests = []

    class Service(rpc.V3DataLiveChatMessageServiceServicer):
        async def StreamList(self, request, context):
            requests.append(request)
            assert dict(context.invocation_metadata())["x-goog-api-key"] == "test-secret"
            try:
                yield proto.LiveChatMessageListResponse(
                    items=[message("old", published=datetime.now(UTC) - timedelta(minutes=1))],
                    next_page_token="next",
                )
                yield proto.LiveChatMessageListResponse(
                    items=[message("new", "current")], next_page_token="last"
                )
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    server = grpc.aio.server()
    rpc.add_V3DataLiveChatMessageServiceServicer_to_server(Service(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    assert port
    await server.start()
    channels = []

    def channel(target, credentials):
        assert target == "youtube.googleapis.com:443"
        assert credentials is not None
        connection = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        channels.append(connection)
        return connection

    monkeypatch.setattr(youtube.grpc.aio, "secure_channel", channel)
    task = asyncio.create_task(stream.run())
    try:
        event = await asyncio.wait_for(queue.get(), 3)
        assert event.comment == "current" and event.platform == "youtube"
        assert queue.empty()
        assert broadcaster.status.youtube.state == "connected"
        assert broadcaster.status.youtube.live.viewers == 123
        assert broadcaster.status.youtube.live.likes == 456
        assert requests[0].live_chat_id == "chat"
        assert list(requests[0].part) == ["id", "snippet", "authorDetails"]
        await cancel(task)
        await asyncio.wait_for(cancelled.wait(), 2)
        assert clients[0].is_closed
        assert stream.page_token == "last"
        with pytest.raises(grpc.aio.UsageError):
            await channels[0].channel_ready()
    finally:
        if not task.done():
            await cancel(task)
        await server.stop(None)


@pytest.mark.parametrize(
    "code",
    [
        grpc.StatusCode.UNAUTHENTICATED,
        grpc.StatusCode.PERMISSION_DENIED,
    ],
)
async def test_terminal_grpc_errors_do_not_retry_or_leak(pipeline, monkeypatch, caplog, code):
    stream, _, broadcaster = pipeline
    clients = install_http(monkeypatch, live_video)
    receive = AsyncMock(
        side_effect=grpc.aio.AioRpcError(code, (), (), "test-secret private-payload")
    )
    monkeypatch.setattr(stream, "_receive", receive)
    task = asyncio.create_task(stream.run())
    try:
        await wait_for_status(broadcaster, "error")
        await asyncio.sleep(0.01)
        assert receive.await_count == 1
        assert "test-secret" not in broadcaster.status.model_dump_json()
        assert "private-payload" not in caplog.text
        assert broadcaster.status.state == "connected"
    finally:
        await cancel(task)
    assert clients[0].is_closed


async def test_missing_key_never_opens_network(pipeline, monkeypatch):
    stream, _, broadcaster = pipeline
    stream.config.youtube_api_key = SecretStr("")
    client = AsyncMock()
    monkeypatch.setattr(youtube.httpx, "AsyncClient", client)
    task = asyncio.create_task(stream.run())
    try:
        await wait_for_status(broadcaster, "error")
        assert "YOUTUBE_API_KEY" in broadcaster.status.youtube.message
        client.assert_not_called()
    finally:
        await cancel(task)


@pytest.mark.parametrize("lookup", ["ended", "disabled", "failed", "still_live"])
async def test_grpc_precondition_checks_video_without_misreporting_permissions(
    pipeline, monkeypatch, caplog, lookup
):
    stream, _, broadcaster = pipeline
    calls = 0

    def video(request):
        nonlocal calls
        calls += 1
        if calls == 1 or lookup == "still_live":
            return live_video(request)
        if lookup == "failed":
            return httpx.Response(503, text="test-secret private-payload")
        details = {"actualStartTime": "started"}
        if lookup == "ended":
            details["actualEndTime"] = "ended"
        return httpx.Response(200, json={"items": [{"liveStreamingDetails": details}]})

    clients = install_http(monkeypatch, video)
    receive = AsyncMock(
        side_effect=grpc.aio.AioRpcError(
            grpc.StatusCode.FAILED_PRECONDITION, (), (), "Precondition check failed"
        )
    )
    monkeypatch.setattr(stream, "_receive", receive)
    task = asyncio.create_task(stream.run())
    try:
        await wait_for_status(broadcaster, "waiting" if lookup == "ended" else "error")
        status = broadcaster.status.youtube
        assert status.live.state == ("ended" if lookup == "ended" else "unknown")
        assert "종료" in status.message if lookup != "disabled" else "비활성화" in status.message
        assert "권한" not in status.message and "할당량" not in status.message
        assert calls == 2
        await asyncio.sleep(0.01)
        receive.assert_awaited_once()
        assert broadcaster.status.state == "connected"
        assert "test-secret" not in broadcaster.status.model_dump_json() + caplog.text
        assert "private-payload" not in caplog.text
    finally:
        await cancel(task)
    assert clients[0].is_closed


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_video_auth_and_quota_errors_stop_requests(pipeline, monkeypatch, caplog, status):
    stream, _, broadcaster = pipeline
    requests = []

    def failure(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": "private-payload test-secret"}})

    install_http(monkeypatch, failure)
    task = asyncio.create_task(stream.run())
    try:
        await wait_for_status(broadcaster, "error")
        await asyncio.sleep(0.01)
        assert len(requests) == 1
        assert "할당량" in broadcaster.status.youtube.message
        assert "private-payload" not in caplog.text
    finally:
        await cancel(task)


async def test_quiet_connected_stream_does_not_time_out(pipeline, monkeypatch):
    stream, _, _ = pipeline
    install_http(monkeypatch, live_video)
    monkeypatch.setattr(youtube, "CONNECT_TIMEOUT_SECONDS", 0.001)
    reading = asyncio.Event()

    async def read():
        reading.set()
        await asyncio.Event().wait()

    call = MagicMock()
    call.read = AsyncMock(side_effect=read)
    channel = AsyncMock()
    channel.__aenter__.return_value = channel
    stub = MagicMock()
    stub.StreamList.return_value = call
    monkeypatch.setattr(youtube.grpc.aio, "secure_channel", MagicMock(return_value=channel))
    monkeypatch.setattr(youtube, "V3DataLiveChatMessageServiceStub", MagicMock(return_value=stub))
    task = asyncio.create_task(stream.run())
    try:
        await asyncio.wait_for(reading.wait(), 1)
        await asyncio.sleep(0.02)
        assert not task.done()
        call.read.assert_awaited_once()
        call.cancel.assert_not_called()
        stub.StreamList.assert_called_once()
    finally:
        await cancel(task)
    call.cancel.assert_called_once()


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"items": []}, "찾을 수 없습니다"),
        ({"items": [{}]}, "실시간 YouTube"),
        ({"items": [{"liveStreamingDetails": {"actualStartTime": "started"}}]}, "비활성화"),
        ({"items": [{"liveStreamingDetails": {"actualEndTime": "ended"}}]}, "종료"),
    ],
)
async def test_unavailable_video_has_terminal_reason(pipeline, payload, expected):
    stream, _, _ = pipeline
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(YouTubeUnavailable, match=expected):
            await stream._chat_id(client)


async def test_scheduled_video_waits_then_connects(pipeline, monkeypatch):
    stream, _, broadcaster = pipeline
    calls = 0

    def video(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200, json={"items": [{"liveStreamingDetails": {"scheduledStartTime": "later"}}]}
            )
        return live_video(request)

    install_http(monkeypatch, video)
    monkeypatch.setattr(youtube, "VIDEO_WAIT_SECONDS", 0.01)
    connected = asyncio.Event()

    async def receive(chat_id, key, client):
        assert chat_id == "chat" and key == "test-secret"
        connected.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(stream, "_receive", receive)
    task = asyncio.create_task(stream.run())
    try:
        await wait_for_status(broadcaster, "waiting")
        await asyncio.wait_for(connected.wait(), 2)
        assert calls == 2
    finally:
        await cancel(task)


@pytest.mark.parametrize("code", [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.RESOURCE_EXHAUSTED])
async def test_transient_failure_retries_safely(pipeline, monkeypatch, caplog, code):
    stream, queue, broadcaster = pipeline
    install_http(monkeypatch, live_video)
    stream.delay = 0.001
    monkeypatch.setattr(youtube, "RETRY_MAX_SECONDS", 0.002)
    retried = asyncio.Event()
    calls = 0

    async def receive(chat_id, key, client):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise grpc.aio.AioRpcError(code, (), (), "test-secret private-payload")
        stream.sink.status("connected", "YouTube LIVE 연결됨")
        stream.sink.publish(parse_comment(message(text="recovered")))
        retried.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(stream, "_receive", receive)
    task = asyncio.create_task(stream.run())
    try:
        await asyncio.wait_for(retried.wait(), 2)
        assert calls == 2
        assert queue.get_nowait().comment == "recovered"
        assert broadcaster.status.youtube.state == "connected"
        assert "test-secret" not in caplog.text
        assert "private-payload" not in caplog.text
        assert broadcaster.status.state == "connected"
    finally:
        await cancel(task)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("123", 123),
        (0, 0),
        ("0", 0),
        ("9007199254740991", 9_007_199_254_740_991),
        (None, None),
        ("", None),
        (True, None),
        (False, None),
        (-1, None),
        ("-1", None),
        (1.5, None),
        ("1.5", None),
        ("1e3", None),
        (" 1 ", None),
        ("１２", None),
        ([], None),
        ({}, None),
        (9_007_199_254_740_992, None),
        ("9007199254740992", None),
        ("1" * 5000, None),
    ],
)
def test_video_metrics_accept_only_safe_nonnegative_counts(value, expected):
    info = parse_live(
        {"liveStreamingDetails": {"concurrentViewers": value}, "statistics": {"likeCount": value}}
    )
    assert info.state == "live"
    assert info.viewers == info.likes == expected


@pytest.mark.parametrize("part", [None, "invalid", [], {}])
def test_video_metrics_missing_or_malformed_parts_are_unknown(part):
    info = parse_live({"liveStreamingDetails": part, "statistics": part})
    assert info.viewers is None and info.likes is None
    info = parse_live(
        {"liveStreamingDetails": {"concurrentViewers": "bad"}, "statistics": {"likeCount": "0"}}
    )
    assert info.viewers is None and info.likes == 0


def test_ended_video_does_not_claim_current_viewers():
    info = parse_live(
        {
            "liveStreamingDetails": {
                "actualEndTime": "2026-11-05T00:00:00Z",
                "concurrentViewers": "42",
            },
            "statistics": {"likeCount": "123"},
        }
    )
    assert info.state == "ended" and info.viewers is None and info.likes == 123


async def eventually(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.001)


def fake_chat(monkeypatch, calls):
    channel = AsyncMock()
    channel.__aenter__.return_value = channel
    stub = MagicMock()
    stub.StreamList.side_effect = calls
    monkeypatch.setattr(youtube.grpc.aio, "secure_channel", MagicMock(return_value=channel))
    monkeypatch.setattr(youtube, "V3DataLiveChatMessageServiceStub", MagicMock(return_value=stub))
    return stub


def chat_responses(token):
    responses = asyncio.Queue()
    responses.put_nowait(proto.LiveChatMessageListResponse(next_page_token=token))
    call = MagicMock()
    call.read = AsyncMock(side_effect=responses.get)
    return call, responses


@pytest.mark.parametrize("failure", [503, 403, "malformed"])
async def test_metrics_refresh_failure_recovery_and_cancellation_do_not_interrupt_chat(
    pipeline, monkeypatch, caplog, failure
):
    stream, queue, broadcaster = pipeline
    monkeypatch.setattr(youtube, "METRICS_INTERVAL_SECONDS", 0.01)
    failed_request, allow_failure, allow_recovery = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    last_request, cancelled_request = asyncio.Event(), asyncio.Event()
    requests = 0
    diagnostics = MagicMock()
    monkeypatch.setattr(stream.sink, "diagnostic", diagnostics)

    async def video(request):
        nonlocal requests
        requests += 1
        if requests == 1:
            return live_video(request)
        if requests == 2:
            failed_request.set()
            await allow_failure.wait()
            return httpx.Response(
                200 if failure == "malformed" else failure,
                json={"items": "private-payload test-secret"},
            )
        if requests == 3:
            await allow_recovery.wait()
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "liveStreamingDetails": {"concurrentViewers": "0"},
                            "statistics": {"likeCount": "789"},
                        }
                    ]
                },
            )
        last_request.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled_request.set()

    clients = install_http(monkeypatch, video)
    call, responses = chat_responses("first")
    stub = fake_chat(monkeypatch, [call])
    task = asyncio.create_task(stream.run())
    try:
        await wait_for_status(broadcaster, "connected")
        assert broadcaster.status.youtube.live.viewers == 123
        assert broadcaster.status.youtube.live.likes == 456
        await asyncio.wait_for(failed_request.wait(), 2)
        # A slow metrics request never holds the chat reader.
        responses.put_nowait(
            proto.LiveChatMessageListResponse(items=[message("during", "during metrics")])
        )
        assert (await asyncio.wait_for(queue.get(), 2)).comment == "during metrics"
        allow_failure.set()
        await eventually(lambda: broadcaster.status.youtube.live.likes is None)
        assert broadcaster.status.youtube.live.viewers is None
        assert broadcaster.status.youtube.live.state == "live"
        assert (
            broadcaster.status.youtube.state == "connected"
            and broadcaster.status.state == "connected"
        )
        assert diagnostics.call_args.args[0] == "youtube_metrics_failed"
        assert "private-payload" not in repr(diagnostics.call_args_list) + caplog.text
        assert "test-secret" not in repr(diagnostics.call_args_list) + caplog.text
        allow_recovery.set()
        await eventually(lambda: broadcaster.status.youtube.live.likes == 789)
        assert broadcaster.status.youtube.live.viewers == 0
        assert not task.done() and stub.StreamList.call_count == 1
        call.cancel.assert_not_called()
        await asyncio.wait_for(last_request.wait(), 2)
        await cancel(task)
        await asyncio.wait_for(cancelled_request.wait(), 2)
        assert clients[0].is_closed
        call.cancel.assert_called_once()
        assert not any(task.get_name() == "youtube-metrics" for task in asyncio.all_tasks())
    finally:
        if not task.done():
            await cancel(task)


async def test_reconnect_cancels_old_metrics_request_before_starting_new_attempt(
    pipeline, monkeypatch
):
    stream, _, broadcaster = pipeline
    monkeypatch.setattr(youtube, "METRICS_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(youtube, "RETRY_MIN_SECONDS", 0.001)
    polling, old_cancelled = asyncio.Event(), asyncio.Event()
    requests = 0

    async def video(request):
        nonlocal requests
        requests += 1
        if requests == 1:
            return live_video(request)
        if requests == 2:
            polling.set()
            try:
                await asyncio.Event().wait()
            finally:
                old_cancelled.set()
        assert old_cancelled.is_set()
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "liveStreamingDetails": {
                            "activeLiveChatId": "chat",
                            "concurrentViewers": "800",
                        },
                        "statistics": {"likeCount": "900"},
                    }
                ]
            },
        )

    clients = install_http(monkeypatch, video)
    first, responses = chat_responses("first")
    second, _ = chat_responses("second")
    stub = fake_chat(monkeypatch, [first, second])
    task = asyncio.create_task(stream.run())
    try:
        await asyncio.wait_for(polling.wait(), 2)
        responses.put_nowait(grpc.aio.EOF)
        await eventually(lambda: broadcaster.status.youtube.live.likes == 900)
        assert broadcaster.status.youtube.live.viewers == 800
        assert old_cancelled.is_set() and stub.StreamList.call_count == 2
        assert stub.StreamList.call_args.args[0].page_token == "first"
        first.cancel.assert_called_once()
        second.cancel.assert_not_called()
        assert sum(task.get_name() == "youtube-metrics" for task in asyncio.all_tasks()) == 1
    finally:
        await cancel(task)
    assert clients[0].is_closed
    assert not any(task.get_name() == "youtube-metrics" for task in asyncio.all_tasks())
