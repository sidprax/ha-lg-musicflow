"""Tests for the finite-file HTTP streaming server."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COMPONENTS = ROOT / "custom_components"
INTEGRATION = CUSTOM_COMPONENTS / "lg_musicflow"

custom_components = sys.modules.setdefault(
    "custom_components", types.ModuleType("custom_components")
)
custom_components.__path__ = [str(CUSTOM_COMPONENTS)]
lg_musicflow = sys.modules.setdefault(
    "custom_components.lg_musicflow", types.ModuleType("custom_components.lg_musicflow")
)
lg_musicflow.__path__ = [str(INTEGRATION)]

homeassistant = types.ModuleType("homeassistant")
homeassistant.__path__ = []
homeassistant_core = types.ModuleType("homeassistant.core")
homeassistant_core.HomeAssistant = object
homeassistant_helpers = types.ModuleType("homeassistant.helpers")
homeassistant_helpers.__path__ = []
homeassistant_aiohttp = types.ModuleType("homeassistant.helpers.aiohttp_client")
homeassistant_aiohttp.async_get_clientsession = lambda hass: None
sys.modules.setdefault("homeassistant", homeassistant)
sys.modules.setdefault("homeassistant.core", homeassistant_core)
sys.modules.setdefault("homeassistant.helpers", homeassistant_helpers)
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", homeassistant_aiohttp)

stream_module = importlib.import_module("custom_components.lg_musicflow.stream")
LGMusicFlowStreamManager = stream_module.LGMusicFlowStreamManager
PreparedStream = stream_module.PreparedStream
finite_stream_url = stream_module.finite_stream_url


class StreamUrlTests(unittest.TestCase):
    """Verify Music Assistant flow URLs resolve to the same finite queue item."""

    def test_rewrites_only_flow_path_segment(self) -> None:
        flow_url = (
            "http://10.0.2.52:8097/flow/session/queue/item/"
            "media_player.darkbar.mp3?token=abc"
        )
        self.assertEqual(
            finite_stream_url(flow_url),
            "http://10.0.2.52:8097/single/session/queue/item/"
            "media_player.darkbar.mp3?token=abc",
        )

    def test_preserves_non_flow_url(self) -> None:
        url = "http://10.0.2.52:8123/local/test.mp3"
        self.assertEqual(finite_stream_url(url), url)


class FakeHass:
    """Minimal executor surface used by the stream manager."""

    async def async_add_executor_job(self, target, *args):
        """Run blocking work off the event loop."""
        return await asyncio.to_thread(target, *args)


class StreamServerTests(unittest.IsolatedAsyncioTestCase):
    """Verify exact HEAD and byte-range responses."""

    async def asyncSetUp(self) -> None:
        descriptor, raw_path = tempfile.mkstemp(prefix="lg-musicflow-test-")
        self.path = Path(raw_path)
        os.close(descriptor)
        await asyncio.to_thread(self.path.write_bytes, b"0123456789abcdef")

        self.manager = LGMusicFlowStreamManager(FakeHass(), port=0)
        await self.manager.async_start()
        self.addAsyncCleanup(self.manager.async_stop)
        self.object_id = "123456789"
        self.manager._entries[self.object_id] = PreparedStream(
            object_id=self.object_id,
            url="unused",
            path=self.path,
            upstream_url=None,
            content_type="audio/mpeg",
            size=16,
            allowed_host="127.0.0.1",
            expires_at=time.monotonic() + 60,
        )
        self.port = self.manager._server.sockets[0].getsockname()[1]
        self.media_path = f"/audio-item-{self.manager.server_uuid}-{self.object_id}"

    async def _request(
        self, request: bytes, body_size: int = 0
    ) -> tuple[list[str], bytes]:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(request)
        await writer.drain()
        raw_headers = await reader.readuntil(b"\r\n\r\n")
        body = await reader.readexactly(body_size) if body_size else b""
        writer.close()
        await writer.wait_closed()
        return raw_headers.decode("latin-1").split("\r\n")[:-2], body

    async def test_head_matches_expected_response(self) -> None:
        headers, body = await self._request(
            (
                f"HEAD {self.media_path} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                "Accept: */*\r\n\r\n"
            ).encode("ascii")
        )

        self.assertEqual(
            headers,
            [
                "HTTP/1.1 200 OK",
                "Connection: Keep-Alive",
                "Content-Type: audio/mpeg",
                "Accept-Ranges: bytes",
                "Content-Length: 16",
            ],
        )
        self.assertEqual(body, b"")

    async def test_get_serves_exact_byte_range(self) -> None:
        headers, body = await self._request(
            (
                f"GET {self.media_path} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                "Range: bytes=2-5\r\n"
                "getcontentFeatures.dlna.org: 1\r\n"
                "transferMode.dlna.org: Streaming\r\n\r\n"
            ).encode("ascii"),
            body_size=4,
        )

        self.assertEqual(
            headers,
            [
                "HTTP/1.1 206 Partial Content",
                "Connection: Keep-Alive",
                "Content-Type: audio/mpeg",
                "Content-Range: bytes 2-5/16",
                "Content-Length: 4",
                "Accept-Ranges: bytes",
            ],
        )
        self.assertEqual(body, b"2345")

    async def test_music_assistant_flow_registers_as_finite_mp3(self) -> None:
        prepared = await self.manager.async_prepare(
            "http://127.0.0.1:8097/flow/session/queue/item/player.mp3",
            allowed_host="127.0.0.1",
            duration=10,
        )

        self.assertIsNone(prepared.path)
        self.assertEqual(
            prepared.upstream_url,
            "http://127.0.0.1:8097/single/session/queue/item/player.mp3",
        )
        self.assertEqual(prepared.content_type, "audio/mpeg")
        self.assertEqual(prepared.size, 400_000)

    async def test_upstream_range_discards_prefix_and_limits_output(self) -> None:
        class FakeContent:
            async def iter_chunked(self, chunk_size):
                del chunk_size
                for chunk in (b"012", b"345", b"6789"):
                    yield chunk

        class FakeResponse:
            status = 200
            content = FakeContent()

            def close(self):
                return None

        class FakeSession:
            async def get(self, url, **kwargs):
                del url, kwargs
                return FakeResponse()

        class FakeWriter:
            def __init__(self):
                self.body = bytearray()

            def write(self, data):
                self.body.extend(data)

            async def drain(self):
                return None

        original_get_session = stream_module.async_get_clientsession
        stream_module.async_get_clientsession = lambda hass: FakeSession()
        self.addCleanup(
            setattr,
            stream_module,
            "async_get_clientsession",
            original_get_session,
        )
        writer = FakeWriter()

        await self.manager._async_send_upstream_range(
            writer,
            "http://unused/single/item.mp3",
            start=2,
            length=4,
        )

        self.assertEqual(bytes(writer.body), b"2345")

    async def test_id3v1_probe_does_not_render_entire_upstream(self) -> None:
        """The SJ9's ID3v1 probe is answered without traversing a live stream."""

        class FakeWriter:
            def __init__(self):
                self.body = bytearray()

            def write(self, data):
                self.body.extend(data)

            async def drain(self):
                return None

        entry = PreparedStream(
            object_id="987654321",
            url="unused",
            path=None,
            upstream_url="http://unused/single/item.mp3",
            content_type="audio/mpeg",
            size=400_000,
            allowed_host="127.0.0.1",
            expires_at=time.monotonic() + 60,
        )
        writer = FakeWriter()
        self.manager._async_send_upstream_range = AsyncMock()

        await self.manager._async_send_file(
            writer,
            entry,
            start=399_872,
            end=399_999,
            partial=True,
        )

        _, body = bytes(writer.body).split(b"\r\n\r\n", 1)
        self.assertEqual(body, bytes(128))
        self.manager._async_send_upstream_range.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
