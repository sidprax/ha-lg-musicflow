"""Tests for the LG Music Flow wire protocol and persistent client."""

from __future__ import annotations

import asyncio
import importlib
import struct
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COMPONENTS = ROOT / "custom_components"
INTEGRATION = CUSTOM_COMPONENTS / "lg_musicflow"

# Import submodules without executing the Home Assistant-dependent package initializer.
custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(CUSTOM_COMPONENTS)]
sys.modules.setdefault("custom_components", custom_components)
lg_musicflow = types.ModuleType("custom_components.lg_musicflow")
lg_musicflow.__path__ = [str(INTEGRATION)]
sys.modules.setdefault("custom_components.lg_musicflow", lg_musicflow)

protocol = importlib.import_module("custom_components.lg_musicflow.protocol")
client_module = importlib.import_module("custom_components.lg_musicflow.client")

LGMusicFlowClient = client_module.LGMusicFlowClient
decode_payload = protocol.decode_payload
encode_frame = protocol.encode_frame


class ProtocolFrameTests(unittest.TestCase):
    """Verify byte-level compatibility with the known LG AES framing."""

    def test_encrypted_frame_matches_known_fixture(self) -> None:
        frame = encode_frame({"msg": "PLAY_INFO_REQ"})

        frame_type, size = struct.unpack(">BI", frame[:5])
        self.assertEqual(frame_type, 0x10)
        self.assertEqual(size, 32)
        self.assertEqual(
            frame[5:].hex(),
            "10921be7f40b8a89bb6edcfb3e10016e7ee7c476f5a0955d321ad13e81adff81",
        )
        self.assertEqual(
            decode_payload(frame_type, frame[5:]),
            {"msg": "PLAY_INFO_REQ"},
        )

    def test_plaintext_frame_remains_available_for_setup_compatibility(self) -> None:
        frame = encode_frame({"msg": "FUNC_INFO_REQ"}, encrypted=False)

        frame_type, size = struct.unpack(">BI", frame[:5])
        self.assertEqual(frame_type, 0x00)
        self.assertEqual(size, len(frame) - 5)
        self.assertTrue(frame.endswith(b"\n"))
        self.assertEqual(
            decode_payload(frame_type, frame[5:]),
            {"msg": "FUNC_INFO_REQ"},
        )


class PersistentClientTests(unittest.IsolatedAsyncioTestCase):
    """Verify response correlation and connection reuse."""

    async def asyncSetUp(self) -> None:
        self.connection_count = 0
        self.received_messages: list[str] = []

        async def handle_client(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            self.connection_count += 1
            try:
                for expected in ("FUNC_INFO_REQ", "PLAY_INFO_REQ"):
                    header = await reader.readexactly(5)
                    frame_type, size = struct.unpack(">BI", header)
                    request = decode_payload(
                        frame_type,
                        await reader.readexactly(size),
                    )
                    self.received_messages.append(request["msg"])
                    self.assertEqual(request["msg"], expected)

                    writer.write(
                        encode_frame({"msg": "PLAY_INFO", "data": {"playing": 4}})
                    )
                    writer.write(
                        encode_frame(
                            {
                                "result": "OK",
                                "msg": expected,
                                "data": {"sequence": len(self.received_messages)},
                            }
                        )
                    )
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        self.server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
        self.addAsyncCleanup(self._close_server)
        port = self.server.sockets[0].getsockname()[1]
        self.client = LGMusicFlowClient("127.0.0.1", port, timeout=1.0)
        self.addAsyncCleanup(self.client.async_close)

    async def _close_server(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def test_reuses_socket_and_skips_unsolicited_broadcasts(self) -> None:
        first = await self.client.async_send_command("FUNC_INFO_REQ")
        second = await self.client.async_send_command("PLAY_INFO_REQ")

        self.assertEqual(first["data"]["sequence"], 1)
        self.assertEqual(second["data"]["sequence"], 2)
        self.assertEqual(self.connection_count, 1)
        self.assertEqual(
            self.received_messages,
            ["FUNC_INFO_REQ", "PLAY_INFO_REQ"],
        )
        self.assertEqual(
            [message["msg"] for message in self.client.drain_broadcasts()],
            ["PLAY_INFO", "PLAY_INFO"],
        )


class CommandTimeoutTests(unittest.IsolatedAsyncioTestCase):
    """Verify command-specific timeout handling."""

    async def test_command_can_override_default_timeout(self) -> None:
        async def handle_client(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            try:
                header = await reader.readexactly(5)
                frame_type, size = struct.unpack(">BI", header)
                request = decode_payload(frame_type, await reader.readexactly(size))
                await asyncio.sleep(0.2)
                writer.write(encode_frame({"result": "OK", "msg": request["msg"]}))
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
        self.addAsyncCleanup(server.wait_closed)
        self.addCleanup(server.close)
        port = server.sockets[0].getsockname()[1]
        client = LGMusicFlowClient("127.0.0.1", port, timeout=0.1)
        self.addAsyncCleanup(client.async_close)

        response = await client.async_send_command("SLOW_COMMAND", timeout=0.5)

        self.assertEqual(response["result"], "OK")


class PlaybackSequenceTests(unittest.IsolatedAsyncioTestCase):
    """Verify the controller playback sequence for media playback."""

    async def test_matches_successful_playback_sequence(self) -> None:
        received: list[dict[str, object]] = []
        media_url = "http://10.0.2.52:8192/audio-item-test-7"

        async def receive_request(
            reader: asyncio.StreamReader,
        ) -> dict[str, object]:
            header = await reader.readexactly(5)
            frame_type, size = struct.unpack(">BI", header)
            return decode_payload(frame_type, await reader.readexactly(size))

        async def respond(
            writer: asyncio.StreamWriter,
            message: dict[str, object],
        ) -> None:
            writer.write(encode_frame(message))
            await writer.drain()

        async def handle_client(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            try:
                request = await receive_request(reader)
                received.append(request)
                await respond(
                    writer,
                    {"result": "OK", "msg": "PLAY_TIME_SET"},
                )

                request = await receive_request(reader)
                received.append(request)
                await respond(
                    writer,
                    {
                        "result": "OK",
                        "msg": "PLAYLIST_TRANS_REQ",
                        "data": {
                            "playlist": [],
                            "startidx": 0,
                            "totalsize": 0,
                            "cursize": 0,
                        },
                    },
                )

                request = await receive_request(reader)
                received.append(request)
                queued_item = request["data"]["item"][0]
                await respond(writer, {"msg": "PLAYLIST_CHANGE"})
                await respond(writer, {"result": "OK", "msg": "ADD_PLAYLIST"})

                request = await receive_request(reader)
                received.append(request)
                await respond(
                    writer,
                    {
                        "result": "OK",
                        "msg": "PLAYLIST_TRANS_REQ",
                        "data": {
                            "playlist": [queued_item],
                            "startidx": 0,
                            "totalsize": 1,
                            "cursize": 1,
                        },
                    },
                )

                request = await receive_request(reader)
                received.append(request)
                await respond(
                    writer,
                    {
                        "result": "OK",
                        "msg": "PLAY_INFO",
                        "data": {"playing": 4, "uri": media_url},
                    },
                )
                await respond(writer, {"result": "OK", "msg": "LOCAL_PLAY_URL"})
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
        self.addAsyncCleanup(server.wait_closed)
        self.addCleanup(server.close)
        port = server.sockets[0].getsockname()[1]
        client = LGMusicFlowClient("127.0.0.1", port, timeout=1.0)
        self.addAsyncCleanup(client.async_close)

        await client.async_play_media(
            media_url,
            title="Test track",
            artist="Test artist",
            duration=197,
            object_id="7",
        )

        self.assertEqual(
            [request["msg"] for request in received],
            [
                "PLAY_TIME_SET",
                "PLAYLIST_TRANS_REQ",
                "ADD_PLAYLIST",
                "PLAYLIST_TRANS_REQ",
                "LOCAL_PLAY_URL",
            ],
        )
        add_data = received[2]["data"]
        self.assertEqual(add_data["position"], 0)
        self.assertEqual(add_data["cursize"], 0)
        self.assertEqual(add_data["totalsize"], 1)
        self.assertEqual(add_data["item"][0]["duration"], 197)
        self.assertEqual(add_data["item"][0]["objID"], "7")

        local_data = received[4]["data"]
        self.assertEqual(local_data["position"], 0)
        self.assertEqual(local_data["item"]["duration"], 0)
        self.assertEqual(local_data["item"]["uri"], media_url)
        self.assertEqual(
            [message["msg"] for message in client.drain_broadcasts()],
            ["PLAYLIST_CHANGE", "PLAY_INFO"],
        )


if __name__ == "__main__":
    unittest.main()
