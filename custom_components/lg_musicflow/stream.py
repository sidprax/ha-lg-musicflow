"""Finite-file streaming server for legacy LG Music Flow speakers."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import mimetypes
import os
import re
import secrets
import socket
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

STREAM_PORT = 8192
STREAM_TTL_SECONDS = 15 * 60
MAX_STREAM_BYTES = 256 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 180
REQUEST_HEADER_LIMIT = 32 * 1024
MP3_BYTES_PER_SECOND = 320_000 // 8
ID3V1_TAG_BYTES = 128
_MEDIA_PATH = re.compile(r"^/audio-item-([0-9a-f-]{36})-(\d+)$", re.IGNORECASE)


class LGMusicFlowStreamError(RuntimeError):
    """Raised when a finite stream cannot be prepared."""


def finite_stream_url(url: str) -> str:
    """Resolve a Music Assistant queue-flow URL to its current finite item."""
    parsed = urlsplit(url)
    if "/flow/" not in parsed.path:
        return url
    return urlunsplit(
        parsed._replace(path=parsed.path.replace("/flow/", "/single/", 1))
    )


@dataclass(slots=True)
class PreparedStream:
    """A finite stream prepared for one speaker."""

    object_id: str
    url: str
    path: Path | None
    upstream_url: str | None
    content_type: str
    size: int
    allowed_host: str
    expires_at: float


class LGMusicFlowStreamManager:
    """Prepare upstream media and serve the speaker-compatible HTTP streaming contract."""

    def __init__(self, hass: HomeAssistant, port: int = STREAM_PORT) -> None:
        """Initialize the stream manager."""
        self.hass = hass
        self.port = port
        self.server_uuid = str(uuid.uuid4())
        self._server: asyncio.AbstractServer | None = None
        self._entries: dict[str, PreparedStream] = {}
        self._prepare_lock = asyncio.Lock()

    async def async_start(self) -> None:
        """Start the dedicated raw HTTP server once."""
        if self._server is not None:
            return
        try:
            self._server = await asyncio.start_server(
                self._async_handle_client,
                host="0.0.0.0",
                port=self.port,
            )
        except OSError as err:
            raise LGMusicFlowStreamError(
                f"Could not bind LG Music Flow stream server on port {self.port}: {err}"
            ) from err
        _LOGGER.info(
            "LG Music Flow finite stream server listening on port %s", self.port
        )

    async def async_stop(self) -> None:
        """Stop the server and remove all cached media."""
        server = self._server
        self._server = None
        if server is not None:
            server.close()
            await server.wait_closed()
        entries = list(self._entries.values())
        self._entries.clear()
        await asyncio.gather(
            *(
                asyncio.to_thread(self._unlink, entry.path)
                for entry in entries
                if entry.path is not None
            )
        )

    async def async_prepare(
        self,
        upstream_url: str,
        *,
        allowed_host: str,
        content_type_hint: str | None = None,
        duration: int = 0,
    ) -> PreparedStream:
        """Prepare an upstream object for finite range serving."""
        upstream_url = finite_stream_url(upstream_url)
        parsed = urlsplit(upstream_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise LGMusicFlowStreamError("Media URL must be HTTP or HTTPS")
        async with self._prepare_lock:
            await self._async_cleanup_expired()
            await self._async_release_for_host(allowed_host)
            is_music_assistant_mp3 = (
                duration > 0
                and "/single/" in parsed.path
                and parsed.path.casefold().endswith(".mp3")
            )
            if is_music_assistant_mp3:
                return await self._async_register_stream(
                    allowed_host=allowed_host,
                    content_type="audio/mpeg",
                    size=duration * MP3_BYTES_PER_SECOND,
                    upstream_url=upstream_url,
                )
            path: Path | None = None
            response: aiohttp.ClientResponse | None = None
            file_handle = None
            try:
                session = async_get_clientsession(self.hass)
                response = await session.get(
                    upstream_url,
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(
                        total=DOWNLOAD_TIMEOUT_SECONDS,
                        connect=10,
                    ),
                )
                if response.status >= 400:
                    raise LGMusicFlowStreamError(
                        f"Upstream media returned HTTP {response.status}"
                    )

                advertised_size = response.content_length
                if advertised_size is not None and advertised_size > MAX_STREAM_BYTES:
                    raise LGMusicFlowStreamError(
                        f"Media exceeds the {MAX_STREAM_BYTES // (1024 * 1024)} MiB limit"
                    )

                suffix = Path(parsed.path).suffix or ".bin"
                descriptor, raw_path = tempfile.mkstemp(
                    prefix="lg-musicflow-",
                    suffix=suffix,
                )
                path = Path(raw_path)
                file_handle = os.fdopen(descriptor, "wb")
                size = 0
                async for chunk in response.content.iter_chunked(128 * 1024):
                    size += len(chunk)
                    if size > MAX_STREAM_BYTES:
                        raise LGMusicFlowStreamError(
                            f"Media exceeds the {MAX_STREAM_BYTES // (1024 * 1024)} MiB limit"
                        )
                    await asyncio.to_thread(file_handle.write, chunk)
                await asyncio.to_thread(file_handle.flush)
                await asyncio.to_thread(file_handle.close)
                file_handle = None
                if size == 0:
                    raise LGMusicFlowStreamError(
                        "Upstream media returned an empty body"
                    )

                content_type = (
                    response.headers.get("Content-Type", "").split(";", 1)[0].strip()
                    or content_type_hint
                    or mimetypes.guess_type(parsed.path)[0]
                    or "application/octet-stream"
                )
                prepared = await self._async_register_stream(
                    allowed_host=allowed_host,
                    content_type=content_type,
                    size=size,
                    path=path,
                )
                _LOGGER.info(
                    "Prepared %s-byte LG Music Flow object %s for %s",
                    size,
                    prepared.object_id,
                    allowed_host,
                )
                return prepared
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise LGMusicFlowStreamError(
                    f"Could not download media: {err}"
                ) from err
            finally:
                if response is not None:
                    response.release()
                if file_handle is not None:
                    await asyncio.to_thread(file_handle.close)
                if path is not None and not any(
                    entry.path == path for entry in self._entries.values()
                ):
                    await asyncio.to_thread(self._unlink, path)

    async def _async_register_stream(
        self,
        *,
        allowed_host: str,
        content_type: str,
        size: int,
        path: Path | None = None,
        upstream_url: str | None = None,
    ) -> PreparedStream:
        """Register a cached file or Music Assistant stream."""
        object_id = self._new_object_id()
        local_address = await self.hass.async_add_executor_job(
            self._source_address_for,
            allowed_host,
        )
        media_path = f"/audio-item-{self.server_uuid}-{object_id}"
        prepared = PreparedStream(
            object_id=object_id,
            url=f"http://{local_address}:{self.port}{media_path}",
            path=path,
            upstream_url=upstream_url,
            content_type=content_type,
            size=size,
            allowed_host=allowed_host,
            expires_at=time.monotonic() + STREAM_TTL_SECONDS,
        )
        self._entries[object_id] = prepared
        return prepared

    async def async_release(self, object_id: str | None) -> None:
        """Release one prepared object."""
        if object_id is None:
            return
        entry = self._entries.pop(object_id, None)
        if entry is not None and entry.path is not None:
            await asyncio.to_thread(self._unlink, entry.path)

    async def _async_release_for_host(self, host: str) -> None:
        """Release stale objects for one speaker before preparing its next track."""
        object_ids = [
            object_id
            for object_id, entry in self._entries.items()
            if entry.allowed_host == host
        ]
        for object_id in object_ids:
            await self.async_release(object_id)

    async def _async_cleanup_expired(self) -> None:
        """Remove expired cached files."""
        now = time.monotonic()
        object_ids = [
            object_id
            for object_id, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for object_id in object_ids:
            await self.async_release(object_id)

    def _new_object_id(self) -> str:
        """Create a path-safe, hard-to-guess numeric object ID."""
        while True:
            object_id = str(secrets.randbits(63))
            if object_id not in self._entries:
                return object_id

    @staticmethod
    def _source_address_for(host: str) -> str:
        """Determine the local interface address routed to one speaker."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((host, 9))
            return str(probe.getsockname()[0])

    @staticmethod
    def _unlink(path: Path) -> None:
        """Remove a cached file if it still exists."""
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _entry_for_request(
        self,
        target: str,
        peer_host: str,
    ) -> PreparedStream | None:
        """Resolve and authorize one request path."""
        match = _MEDIA_PATH.fullmatch(urlsplit(target).path)
        if match is None or match.group(1).lower() != self.server_uuid.lower():
            return None
        entry = self._entries.get(match.group(2))
        if entry is None or entry.expires_at <= time.monotonic():
            return None
        if ipaddress.ip_address(peer_host) != ipaddress.ip_address(entry.allowed_host):
            return None
        return entry

    async def _async_handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Serve one or more HTTP/1.1 requests from a speaker."""
        peer = writer.get_extra_info("peername")
        peer_host = str(peer[0]) if peer else ""
        try:
            while True:
                try:
                    raw_headers = await asyncio.wait_for(
                        reader.readuntil(b"\r\n\r\n"),
                        timeout=10,
                    )
                except (asyncio.IncompleteReadError, asyncio.TimeoutError):
                    break
                if len(raw_headers) > REQUEST_HEADER_LIMIT:
                    await self._async_write_error(
                        writer, 431, "Request Header Fields Too Large"
                    )
                    break

                try:
                    header_text = raw_headers.decode("latin-1")
                    lines = header_text.split("\r\n")
                    method, target, version = lines[0].split(" ", 2)
                    headers = {
                        key.strip().lower(): value.strip()
                        for line in lines[1:]
                        if ":" in line
                        for key, value in [line.split(":", 1)]
                    }
                except (UnicodeDecodeError, ValueError):
                    await self._async_write_error(writer, 400, "Bad Request")
                    break
                if version != "HTTP/1.1":
                    await self._async_write_error(
                        writer, 505, "HTTP Version Not Supported"
                    )
                    break

                entry = self._entry_for_request(target, peer_host)
                if entry is None:
                    await self._async_write_error(writer, 404, "Not Found")
                    break
                if method == "HEAD":
                    self._write_headers(
                        writer,
                        "200 OK",
                        [
                            ("Connection", "Keep-Alive"),
                            ("Content-Type", entry.content_type),
                            ("Accept-Ranges", "bytes"),
                            ("Content-Length", str(entry.size)),
                        ],
                    )
                    await writer.drain()
                elif method == "GET":
                    byte_range = self._parse_range(headers.get("range"), entry.size)
                    if byte_range is None:
                        await self._async_write_range_error(writer, entry.size)
                        break
                    start, end, partial = byte_range
                    await self._async_send_file(writer, entry, start, end, partial)
                else:
                    await self._async_write_error(writer, 405, "Method Not Allowed")
                    break

                if headers.get("connection", "").lower() == "close":
                    break
        except (
            aiohttp.ClientError,
            LGMusicFlowStreamError,
            BrokenPipeError,
            ConnectionResetError,
            OSError,
        ) as err:
            _LOGGER.debug("LG Music Flow stream connection ended: %s", err)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    @staticmethod
    def _parse_range(
        header: str | None,
        size: int,
    ) -> tuple[int, int, bool] | None:
        """Parse one HTTP byte range."""
        if header is None:
            return 0, size - 1, False
        if not header.startswith("bytes=") or "," in header:
            return None
        left, separator, right = header[6:].partition("-")
        if not separator:
            return None
        try:
            if left:
                start = int(left)
                end = int(right) if right else size - 1
            elif right:
                suffix_length = int(right)
                if suffix_length <= 0:
                    return None
                start = max(0, size - suffix_length)
                end = size - 1
            else:
                return None
        except ValueError:
            return None
        if start < 0 or start >= size or end < start:
            return None
        return start, min(end, size - 1), True

    async def _async_send_file(
        self,
        writer: asyncio.StreamWriter,
        entry: PreparedStream,
        start: int,
        end: int,
        partial: bool,
    ) -> None:
        """Send one full or partial file response."""
        length = end - start + 1
        headers = [
            ("Connection", "Keep-Alive"),
            ("Content-Type", entry.content_type),
        ]
        if partial:
            headers.append(("Content-Range", f"bytes {start}-{end}/{entry.size}"))
        headers.extend(
            [
                ("Content-Length", str(length)),
                ("Accept-Ranges", "bytes"),
            ]
        )
        self._write_headers(
            writer, "206 Partial Content" if partial else "200 OK", headers
        )
        await writer.drain()

        if entry.path is not None:
            await self._async_send_local_range(writer, entry.path, start, length)
        elif entry.upstream_url is not None:
            if start == entry.size - ID3V1_TAG_BYTES and length == ID3V1_TAG_BYTES:
                # The SJ9 checks for an ID3v1 tag before playback. Music Assistant's
                # live stream has no seekable tail, so report that no tag is present.
                writer.write(bytes(ID3V1_TAG_BYTES))
                await writer.drain()
                return
            await self._async_send_upstream_range(
                writer,
                entry.upstream_url,
                start,
                length,
            )
        else:
            raise LGMusicFlowStreamError("Prepared stream has no media source")

    @staticmethod
    async def _async_send_local_range(
        writer: asyncio.StreamWriter,
        path: Path,
        start: int,
        length: int,
    ) -> None:
        """Send a byte range from a cached local file."""
        file_handle = await asyncio.to_thread(path.open, "rb")
        try:
            await asyncio.to_thread(file_handle.seek, start)
            remaining = length
            while remaining:
                chunk = await asyncio.to_thread(
                    file_handle.read, min(128 * 1024, remaining)
                )
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
                remaining -= len(chunk)
        finally:
            await asyncio.to_thread(file_handle.close)

    async def _async_send_upstream_range(
        self,
        writer: asyncio.StreamWriter,
        upstream_url: str,
        start: int,
        length: int,
    ) -> None:
        """Render one range from a finite Music Assistant single-item stream."""
        session = async_get_clientsession(self.hass)
        response = await session.get(
            upstream_url,
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=None, connect=10),
        )
        try:
            if response.status >= 400:
                raise LGMusicFlowStreamError(
                    f"Upstream media returned HTTP {response.status}"
                )
            skip = start
            remaining = length
            async for chunk in response.content.iter_chunked(128 * 1024):
                if skip:
                    skipped = min(skip, len(chunk))
                    chunk = chunk[skipped:]
                    skip -= skipped
                    if not chunk:
                        continue
                if len(chunk) > remaining:
                    chunk = chunk[:remaining]
                writer.write(chunk)
                await writer.drain()
                remaining -= len(chunk)
                if remaining == 0:
                    break
            if remaining:
                _LOGGER.warning(
                    "Music Assistant stream ended %s bytes before its estimated length",
                    remaining,
                )
        finally:
            response.close()

    @staticmethod
    def _write_headers(
        writer: asyncio.StreamWriter,
        status: str,
        headers: list[tuple[str, str]],
    ) -> None:
        """Write an exact HTTP/1.1 status line and ordered headers."""
        lines = [
            f"HTTP/1.1 {status}",
            *(f"{key}: {value}" for key, value in headers),
            "",
            "",
        ]
        writer.write("\r\n".join(lines).encode("latin-1"))

    async def _async_write_error(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        reason: str,
    ) -> None:
        """Write a bodyless error and close the connection."""
        self._write_headers(
            writer,
            f"{status_code} {reason}",
            [("Connection", "close"), ("Content-Length", "0")],
        )
        await writer.drain()

    async def _async_write_range_error(
        self,
        writer: asyncio.StreamWriter,
        size: int,
    ) -> None:
        """Write a 416 response for an invalid range."""
        self._write_headers(
            writer,
            "416 Range Not Satisfiable",
            [
                ("Connection", "close"),
                ("Content-Range", f"bytes */{size}"),
                ("Content-Length", "0"),
            ],
        )
        await writer.drain()
