"""Async client for communicating with LG Music Flow speakers on TCP port 9741."""

from __future__ import annotations

import asyncio
import logging
import struct
from collections import deque
from typing import Any

from .const import (
    DEFAULT_PORT,
    PLAY_CTRL_PAUSE,
    PLAY_CTRL_PLAY,
    PLAY_CTRL_STOP,
)
from .protocol import HEADER_SIZE, decode_payload, encode_frame

_LOGGER = logging.getLogger(__name__)
_PLAYBACK_START_TIMEOUT = 15.0


class LGMusicFlowError(Exception):
    """Base exception for LG Music Flow communication errors."""


class LGMusicFlowClient:
    """Asynchronous client for an LG Music Flow soundbar/speaker."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = 4.0,
        *,
        encrypted: bool = True,
    ) -> None:
        """Initialize the client."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self.encrypted = encrypted
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._broadcasts: deque[dict[str, Any]] = deque(maxlen=100)
        self._next_object_id = 1

    @property
    def connected(self) -> bool:
        """Return whether the persistent control socket is open."""
        return self._writer is not None and not self._writer.is_closing()

    async def _async_connect_locked(self) -> None:
        """Open the persistent control socket while holding the command lock."""
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except (asyncio.TimeoutError, OSError) as err:
            self._reader = None
            self._writer = None
            raise LGMusicFlowError(
                f"Connection to {self.host}:{self.port} failed: {err}"
            ) from err

    async def _async_close_locked(self) -> None:
        """Close the persistent control socket while holding the command lock."""
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass

    async def async_close(self) -> None:
        """Close the persistent speaker connection."""
        async with self._lock:
            await self._async_close_locked()

    def drain_broadcasts(self) -> list[dict[str, Any]]:
        """Return and clear unsolicited messages received between responses."""
        broadcasts = list(self._broadcasts)
        self._broadcasts.clear()
        return broadcasts

    async def _async_read_frame(self, deadline: float) -> dict[str, Any]:
        """Read and decode one frame before the absolute deadline."""
        if self._reader is None:
            raise LGMusicFlowError("Speaker connection is not open")
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError
        header = await asyncio.wait_for(
            self._reader.readexactly(HEADER_SIZE),
            timeout=remaining,
        )
        frame_type, size = struct.unpack(">BI", header)
        if size <= 0 or size > 8 * 1024 * 1024:
            raise LGMusicFlowError(f"Invalid speaker frame length: {size}")
        remaining = deadline - asyncio.get_running_loop().time()
        body = await asyncio.wait_for(
            self._reader.readexactly(size),
            timeout=max(remaining, 0.001),
        )
        return decode_payload(frame_type, body)

    async def async_send_command(
        self,
        msg_type: str,
        data: dict[str, Any] | None = None,
        *,
        expected_msg: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send one request and wait for its matching response."""
        payload: dict[str, Any] = {"msg": msg_type}
        if data is not None:
            payload["data"] = data
        packet = encode_frame(payload, encrypted=self.encrypted)
        expected = expected_msg or msg_type

        async with self._lock:
            try:
                await self._async_connect_locked()
                if self._writer is None:
                    raise LGMusicFlowError("Speaker connection is not open")
                self._writer.write(packet)
                await self._writer.drain()

                response_timeout = self.timeout if timeout is None else timeout
                deadline = asyncio.get_running_loop().time() + response_timeout
                while True:
                    response = await self._async_read_frame(deadline)
                    response_type = response.get("msg")
                    if response_type == "MSG_PARSING_ERROR":
                        raise LGMusicFlowError(
                            f"Speaker rejected {msg_type}: malformed request"
                        )
                    if response_type == expected:
                        result = response.get("result")
                        if result not in (None, "OK", 0, "0"):
                            raise LGMusicFlowError(
                                f"Speaker rejected {msg_type}: {result}"
                            )
                        return response
                    self._broadcasts.append(response)
            except LGMusicFlowError:
                await self._async_close_locked()
                raise
            except (
                asyncio.IncompleteReadError,
                asyncio.TimeoutError,
                ConnectionError,
                OSError,
                ValueError,
            ) as err:
                await self._async_close_locked()
                raise LGMusicFlowError(
                    f"Error communicating with {self.host}:{self.port}: {err}"
                ) from err

    async def async_get_product_info(self) -> dict[str, Any]:
        """Fetch general product information (MAC, supported functions, supported EQ)."""
        res = await self.async_send_command(
            "PRODUCT_INFO",
            {"day": 6, "hour": 4, "id": "and0000000000000000", "min": 34, "option": 0},
        )
        return res.get("data", {})

    async def async_get_status(self) -> dict[str, Any]:
        """Fetch current live state (functions, play info, EQ, settings)."""
        func_res = await self.async_send_command("FUNC_INFO_REQ")
        play_res = await self.async_send_command("PLAY_INFO_REQ")
        eq_res = await self.async_send_command("EQ_INFO_REQ")
        settings_res = await self.async_send_command("SETTING_INFO_REQ")

        return {
            "func": func_res.get("data", {}),
            "play": play_res.get("data", {}),
            "eq": eq_res.get("data", {}),
            "settings": settings_res.get("data", {}),
        }

    async def async_set_volume(self, volume: int) -> None:
        """Set volume level (typically 0 - 40 or 0 - 100)."""
        await self.async_send_command("VOLUME_SETTING", {"vol": volume, "fadetime": 0})

    async def async_set_mute(self, mute: bool) -> None:
        """Set mute state."""
        await self.async_send_command("MUTE_SET", {"mute": mute})

    async def async_set_function(self, func_code: int) -> None:
        """Set source/function mode (0=Wi-Fi, 4=Optical, 6=HDMI, 1=Bluetooth, etc.)."""
        await self.async_send_command("FUNCTION_SET", {"type": func_code})

    async def async_set_sound_mode(self, eq_code: int) -> None:
        """Set sound mode / equalizer preset."""
        await self.async_send_command("EQ_SETTING", {"type": 0, "value": eq_code})

    async def async_set_night_mode(self, night_mode: bool) -> None:
        """Set night mode."""
        await self.async_send_command("NIGHT_MODE_SET", {"nightmode": night_mode})

    async def async_set_auto_power(self, auto_power: bool) -> None:
        """Set auto power (automatic optical standby/switch)."""
        await self.async_send_command("AUTO_POWER_SET", {"autopower": auto_power})

    async def async_set_woofer_level(self, level: int) -> None:
        """Set woofer level (-15 to +6 or as reported by wooferoffset/woofermax)."""
        await self.async_send_command("WOOFER_LEVEL_SET", {"wooferlevel": level})

    async def async_play_media(
        self,
        url: str,
        title: str = "Home Assistant",
        artist: str = "Media Player",
        *,
        duration: int = 0,
        object_id: str | None = None,
    ) -> None:
        """Load one finite media item and begin playback using the controller playback sequence."""
        if object_id is None:
            object_id = str(self._next_object_id)
            self._next_object_id += 1

        await self.async_send_command("PLAY_TIME_SET", {"set": True})

        playlist = await self.async_send_command(
            "PLAYLIST_TRANS_REQ",
            {"all": False, "startidx": 0},
        )
        playlist_data = playlist.get("data", {})
        if playlist_data.get("totalsize", 0):
            await self.async_send_command(
                "DELETE_PLAYLIST",
                {"curIdx": 0, "idx": 0, "type": 2},
            )
            await self.async_send_command(
                "PLAYLIST_TRANS_REQ",
                {"all": False, "startidx": 0},
            )

        playlist_item = {
            "accessToken": "",
            "actionId": "",
            "albumart": "",
            "albumtitle": "",
            "artist": artist,
            "clientType": "",
            "cobrandId": "",
            "contentsType": "",
            "cptype": 0,
            "duration": max(0, int(duration)),
            "exception": "",
            "idx": 0,
            "inactive": False,
            "logon": "",
            "objID": object_id,
            "password": "",
            "playConfirm": False,
            "playing": 0,
            "position": 0,
            "refreshToken": "",
            "repeat": 0,
            "shuffle": False,
            "source": 0,
            "title": title,
            "trackId": "",
            "uri": url,
        }
        await self.async_send_command(
            "ADD_PLAYLIST",
            {
                "cursize": 0,
                "item": [playlist_item],
                "position": 0,
                "startidx": 0,
                "totalsize": 1,
            },
        )
        confirmed = await self.async_send_command(
            "PLAYLIST_TRANS_REQ",
            {"all": False, "startidx": 0},
        )
        confirmed_items = confirmed.get("data", {}).get("playlist", [])
        if not confirmed_items or confirmed_items[0].get("uri") != url:
            raise LGMusicFlowError("Speaker did not retain the queued media item")

        local_item = {**playlist_item, "duration": 0}
        play_req = {
            "add": False,
            "item": local_item,
            "position": 0,
            "sync": False,
            "time": 0,
        }
        await self.async_send_command(
            "LOCAL_PLAY_URL",
            play_req,
            timeout=max(self.timeout, _PLAYBACK_START_TIMEOUT),
        )

    async def async_media_play(self) -> None:
        """Resume playback."""
        await self.async_send_command(
            "PLAY_CMD", {"playctrl": PLAY_CTRL_PLAY, "repeat": 0, "shuffle": False}
        )

    async def async_media_pause(self) -> None:
        """Pause playback."""
        await self.async_send_command(
            "PLAY_CMD", {"playctrl": PLAY_CTRL_PAUSE, "repeat": 0, "shuffle": False}
        )

    async def async_media_stop(self) -> None:
        """Stop playback."""
        await self.async_send_command(
            "PLAY_CMD", {"playctrl": PLAY_CTRL_STOP, "repeat": 0, "shuffle": False}
        )

    async def async_set_name(self, name: str) -> dict[str, Any]:
        """Set / rename the speaker petname."""
        return await self.async_send_command("SPK_INFO_MODIFY", {"name": name})

    async def async_share_home_info(
        self,
        ssid: str,
        password: str,
        auth_type: int = 0,
    ) -> dict[str, Any]:
        """Send Wi-Fi credentials to soundbar for initial provisioning or network switch."""
        return await self.async_send_command(
            "SHARE_HOME_INFO",
            {
                "ssid": ssid,
                "pwd": password,
                "auth": auth_type,
            },
        )
