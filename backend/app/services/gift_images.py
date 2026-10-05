"""Bounded, in-memory cache for gift images observed in LIVE events."""

import asyncio
import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlsplit

import httpx

CDN_DOMAINS = ("tiktokcdn.com", "tiktokcdn-us.com", "tiktokcdn-eu.com")
MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/avif"}
MAX_URLS = 1024
MAX_ENTRIES = 128
MAX_CACHE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_PENDING = 16
MAX_DOWNLOADS = 4
TIMEOUT = 5.0
POSITIVE_TTL = 3600.0
NEGATIVE_TTL = 30.0


@dataclass(frozen=True)
class CachedImage:
    content: bytes
    media_type: str
    etag: str
    expires_at: float


@dataclass(frozen=True)
class CacheEntry:
    image: CachedImage | None
    expires_at: float


def _allowed_url(url: str) -> bool:
    if not url or len(url) > 2048 or any(ord(char) <= 32 for char in url):
        return False
    try:
        parts = urlsplit(url)
        host = parts.hostname
        return (
            parts.scheme == "https"
            and host is not None
            and any(host == domain or host.endswith("." + domain) for domain in CDN_DOMAINS)
            and parts.port in (None, 443)
            and parts.username is None
            and parts.password is None
            and not parts.fragment
        )
    except ValueError:
        return False


def _valid_image(media_type: str, content: bytes) -> bool:
    if media_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if media_type == "image/webp":
        return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    if media_type == "image/gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if media_type == "image/avif":
        return content[4:8] == b"ftyp" and any(
            content[i : i + 4] in (b"avif", b"avis") for i in range(8, min(len(content), 32), 4)
        )
    return False


class GiftImageCache:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client
        self.urls: OrderedDict[str, str] = OrderedDict()
        self.entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self.cache_bytes = 0
        self.inflight: dict[str, asyncio.Task[CachedImage | None]] = {}
        self.downloads = asyncio.Semaphore(MAX_DOWNLOADS)
        self.pending = 0
        self.closed = False

    def register(self, url: str) -> str | None:
        if self.closed or not _allowed_url(url):
            return None
        key = hashlib.sha256(url.encode()).hexdigest()
        self.urls[key] = url
        self.urls.move_to_end(key)
        if len(self.urls) > MAX_URLS:
            self.urls.popitem(last=False)
        return f"/gift-images/{key}"

    async def get(self, key: str) -> CachedImage | None:
        if self.closed or len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
            return None
        url = self.urls.get(key)
        if url is None:
            return None
        self.urls.move_to_end(key)
        entry = self.entries.get(key)
        if entry is not None:
            if entry.expires_at > monotonic():
                self.entries.move_to_end(key)
                return entry.image
            self._remove_entry(key)
        if self.pending >= MAX_PENDING:
            return None
        self.pending += 1
        try:
            task = self.inflight.get(key)
            if task is None:
                if len(self.inflight) >= MAX_PENDING:
                    return None
                task = asyncio.create_task(self._load(key, url))
                self.inflight[key] = task
                task.add_done_callback(lambda finished: self._forget_task(key, finished))
            try:
                async with asyncio.timeout(TIMEOUT):
                    return await asyncio.shield(task)
            except TimeoutError:
                return None
        finally:
            self.pending -= 1

    def _forget_task(self, key: str, task: asyncio.Task[CachedImage | None]) -> None:
        if self.inflight.get(key) is task:
            self.inflight.pop(key, None)

    def _remove_entry(self, key: str) -> None:
        entry = self.entries.pop(key)
        if entry.image is not None:
            self.cache_bytes -= len(entry.image.content)

    def _store(self, key: str, image: CachedImage | None, expires_at: float) -> None:
        if key in self.entries:
            self._remove_entry(key)
        self.entries[key] = CacheEntry(image, expires_at)
        if image is not None:
            self.cache_bytes += len(image.content)
        while len(self.entries) > MAX_ENTRIES or self.cache_bytes > MAX_CACHE_BYTES:
            self._remove_entry(next(iter(self.entries)))

    async def _load(self, key: str, url: str) -> CachedImage | None:
        try:
            async with asyncio.timeout(TIMEOUT):
                async with self.downloads:
                    result = await self._fetch(url)
        except Exception:
            # Upstream errors can include signed URLs; keep them out of logs.
            result = None
        expires_at = monotonic() + (POSITIVE_TTL if result is not None else NEGATIVE_TTL)
        image = (
            CachedImage(
                content=result[0],
                media_type=result[1],
                etag='"' + hashlib.sha256(result[0]).hexdigest() + '"',
                expires_at=expires_at,
            )
            if result is not None
            else None
        )
        if not self.closed:
            self._store(key, image, expires_at)
        return image

    async def _fetch(self, url: str) -> tuple[bytes, str] | None:
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=TIMEOUT, follow_redirects=False, trust_env=False
            )
        async with self.client.stream(
            "GET",
            url,
            headers={"Accept": ", ".join(sorted(MEDIA_TYPES)), "Accept-Encoding": "identity"},
            follow_redirects=False,
        ) as response:
            if response.status_code != 200:
                return None
            media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if (
                media_type not in MEDIA_TYPES
                or response.headers.get("content-encoding", "identity") != "identity"
            ):
                return None
            try:
                if int(response.headers.get("content-length", "0")) > MAX_IMAGE_BYTES:
                    return None
            except ValueError:
                pass
            content = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                if len(content) + len(chunk) > MAX_IMAGE_BYTES:
                    return None
                content.extend(chunk)
            body = bytes(content)
            return (body, media_type) if _valid_image(media_type, body) else None

    async def close(self) -> None:
        self.closed = True
        for task in self.inflight.values():
            task.cancel()
        await asyncio.gather(*self.inflight.values(), return_exceptions=True)
        self.inflight.clear()
        if self.client is not None:
            await self.client.aclose()
        self.urls.clear()
        self.entries.clear()
        self.cache_bytes = 0
