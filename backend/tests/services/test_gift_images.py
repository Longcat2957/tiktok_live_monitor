import asyncio
import gzip
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services import gift_images
from app.services.gift_images import GiftImageCache

PNG = b"\x89PNG\r\n\x1a\n" + b"small-image"
URL = "https://p16.tiktokcdn.com/gift.png?token=private"


def registered(cache: GiftImageCache, url: str = URL) -> tuple[str, str]:
    path = cache.register(url)
    assert path is not None
    return path, path.rsplit("/", 1)[1]


@pytest.mark.parametrize(
    "url",
    [
        "http://p16.tiktokcdn.com/gift.png",
        "https://tiktokcdn.com.evil.test/gift.png",
        "https://evil-tiktokcdn.com/gift.png",
        "https://user:pass@tiktokcdn.com/gift.png",
        "https://tiktokcdn.com:444/gift.png",
        "https://127.0.0.1/gift.png",
        "https://tiktokcdn.com/gift.png#fragment",
    ],
)
def test_only_observed_trusted_cdn_urls_are_registered(url: str) -> None:
    cache = GiftImageCache()
    assert cache.register(url) is None
    assert cache.client is None


async def test_registered_url_is_opaque_and_only_known_keys_are_fetched() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, headers={"Content-Type": "image/png"}, content=PNG)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    cache = GiftImageCache(client)
    try:
        path, key = registered(cache)
        assert "token" not in path
        assert cache.register(URL.replace("private", "different")) != path
        assert cache.register("https://tiktokcdn-us.com/gift.png") is not None
        assert cache.register("https://p1.tiktokcdn-eu.com/gift.png") is not None
        assert await cache.get("0" * 64) is None
        assert await cache.get("not-a-key") is None
        assert requests == []
        image = await cache.get(key)
        assert image is not None and image.content == PNG
        assert len(requests) == 1
        assert str(requests[0].url) == URL
        assert requests[0].headers["Accept-Encoding"] == "identity"
        assert await cache.get(key) is image
        assert len(requests) == 1
    finally:
        await cache.close()


async def test_one_download_serves_concurrent_callers_even_if_one_cancels() -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return httpx.Response(200, headers={"Content-Type": "image/png"}, content=PNG)

    cache = GiftImageCache(httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    _, key = registered(cache)
    first = asyncio.create_task(cache.get(key))
    try:
        await entered.wait()
        second = asyncio.create_task(cache.get(key))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        image = await second
        assert image is not None and image.content == PNG
        assert calls == 1
        assert cache.pending == 0
    finally:
        release.set()
        await cache.close()


async def test_abandoned_downloads_still_count_against_task_limit() -> None:
    release = asyncio.Event()
    started = 0

    async def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal started
        started += 1
        await release.wait()
        return httpx.Response(200, headers={"Content-Type": "image/png"}, content=PNG)

    cache = GiftImageCache(httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    tasks = []
    try:
        for i in range(gift_images.MAX_PENDING):
            _, key = registered(cache, f"https://p16.tiktokcdn.com/{i}.png")
            tasks.append(asyncio.create_task(cache.get(key)))
        await asyncio.sleep(0.01)
        assert len(cache.inflight) == gift_images.MAX_PENDING
        assert started == gift_images.MAX_DOWNLOADS
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert cache.pending == 0
        _, extra_key = registered(cache, "https://p16.tiktokcdn.com/extra.png")
        assert await cache.get(extra_key) is None
        assert len(cache.inflight) == gift_images.MAX_PENDING
    finally:
        await cache.close()
        assert not cache.inflight
        assert cache.client is not None and cache.client.is_closed


async def test_success_and_failure_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(gift_images, "monotonic", lambda: now[0])
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, headers={"Content-Type": "image/png"}, content=PNG)

    cache = GiftImageCache(httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    try:
        _, key = registered(cache)
        assert await cache.get(key) is None
        assert await cache.get(key) is None
        assert calls == 1
        now[0] += gift_images.NEGATIVE_TTL + 1
        assert (await cache.get(key)) is not None
        assert (await cache.get(key)) is not None
        assert calls == 2
        now[0] += gift_images.POSITIVE_TTL + 1
        assert (await cache.get(key)) is not None
        assert calls == 3
    finally:
        await cache.close()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"Location": "http://127.0.0.1/private"}),
        httpx.Response(200, headers={"Content-Type": "image/svg+xml"}, content=PNG),
        httpx.Response(200, headers={"Content-Type": "image/png"}, content=b"not-png"),
        httpx.Response(
            200,
            headers={"Content-Type": "image/png", "Content-Encoding": "gzip"},
            content=gzip.compress(PNG),
        ),
        httpx.Response(
            200,
            headers={
                "Content-Type": "image/png",
                "Content-Length": str(gift_images.MAX_IMAGE_BYTES + 1),
            },
            content=PNG,
        ),
        httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=PNG + b"x" * gift_images.MAX_IMAGE_BYTES,
        ),
    ],
)
async def test_untrusted_or_oversized_responses_are_rejected(response: httpx.Response) -> None:
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response

    cache = GiftImageCache(httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    try:
        _, key = registered(cache)
        assert await cache.get(key) is None
        assert await cache.get(key) is None
        assert calls == 1
    finally:
        await cache.close()


async def test_registry_evicts_oldest_url_without_fetching() -> None:
    cache = GiftImageCache()
    try:
        _, oldest = registered(cache, "https://tiktokcdn.com/0.png")
        for i in range(1, gift_images.MAX_URLS + 1):
            registered(cache, f"https://tiktokcdn.com/{i}.png")
        assert len(cache.urls) == gift_images.MAX_URLS
        assert await cache.get(oldest) is None
        assert cache.client is None
    finally:
        await cache.close()


async def test_cached_images_obey_entry_and_byte_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gift_images, "MAX_ENTRIES", 2)
    monkeypatch.setattr(gift_images, "MAX_CACHE_BYTES", 3 * len(PNG))
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, headers={"Content-Type": "image/png"}, content=PNG)

    cache = GiftImageCache(httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    try:
        keys = [registered(cache, f"https://tiktokcdn.com/{i}.png")[1] for i in range(4)]
        assert await cache.get(keys[0]) is not None
        assert await cache.get(keys[1]) is not None
        assert await cache.get(keys[0]) is not None  # Most recently used survives eviction.
        assert await cache.get(keys[2]) is not None
        assert list(cache.entries) == [keys[0], keys[2]]
        assert cache.cache_bytes == 2 * len(PNG)
        monkeypatch.setattr(gift_images, "MAX_ENTRIES", 4)
        monkeypatch.setattr(gift_images, "MAX_CACHE_BYTES", 2 * len(PNG))
        assert await cache.get(keys[3]) is not None
        assert list(cache.entries) == [keys[2], keys[3]]
        assert cache.cache_bytes == 2 * len(PNG)
        assert calls == 4
    finally:
        await cache.close()


def test_http_image_route_supports_etag_and_unknown_key() -> None:
    app = create_app(Settings(_env_file=None))
    with TestClient(app, base_url="http://localhost") as client:
        cache = app.state.monitor.gift_images
        path, _ = registered(cache)
        fetch = AsyncMock(return_value=(PNG, "image/png"))
        cache._fetch = fetch
        first = client.get(path)
        assert first.status_code == 200 and first.content == PNG
        assert first.headers["content-type"] == "image/png"
        assert first.headers["cache-control"].startswith("public, max-age=")
        assert first.headers["x-content-type-options"] == "nosniff"
        assert client.get(path, headers={"If-None-Match": first.headers["etag"]}).status_code == 304
        assert client.get("/gift-images/" + "0" * 64).status_code == 404
        fetch.assert_awaited_once()
