"""Async client for communicating with LG Music Flow speakers on TCP port 9741."""
import asyncio
import json
import logging
import struct
from typing import Any, Dict, Optional

from .const import (
    DEFAULT_PORT,
    PLAY_CTRL_PAUSE,
    PLAY_CTRL_PLAY,
    PLAY_CTRL_STOP,
)

_LOGGER = logging.getLogger(__name__)


class LGMusicFlowError(Exception):
    """Base exception for LG Music Flow communication errors."""


class LGMusicFlowClient:
    """Asynchronous client for an LG Music Flow soundbar/speaker."""

    def __init__(self, host: str, port: int = DEFAULT_PORT, timeout: float = 3.5) -> None:
        """Initialize the client."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self._lock = asyncio.Lock()

    async def async_send_command(self, msg_type: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a command packet to the soundbar and read the JSON response."""
        payload: Dict[str, Any] = {"msg": msg_type}
        if data is not None:
            payload["data"] = data

        body = json.dumps(payload).encode("utf-8")
        header = struct.pack(">BI", 0x00, len(body))
        packet = header + body

        async with self._lock:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=self.timeout
                )
            except (asyncio.TimeoutError, OSError) as err:
                raise LGMusicFlowError(f"Connection to {self.host}:{self.port} failed: {err}") from err

            try:
                writer.write(packet)
                await writer.drain()

                hdr = await asyncio.wait_for(reader.readexactly(5), timeout=self.timeout)
                _, size = struct.unpack(">BI", hdr)

                resp_data = await asyncio.wait_for(reader.readexactly(size), timeout=self.timeout)
                res_str = resp_data.decode("utf-8", errors="replace")
                return json.loads(res_str)
            except (asyncio.TimeoutError, OSError, json.JSONDecodeError) as err:
                raise LGMusicFlowError(f"Error communicating with {self.host}:{self.port}: {err}") from err
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    async def async_get_product_info(self) -> Dict[str, Any]:
        """Fetch general product information (MAC, supported functions, supported EQ)."""
        res = await self.async_send_command("PRODUCT_INFO", {
            "day": 6,
            "hour": 4,
            "id": "and0000000000000000",
            "min": 34,
            "option": 0
        })
        return res.get("data", {})

    async def async_get_status(self) -> Dict[str, Any]:
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
        await self.async_send_command("MUTE", {"mute": mute})

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

    async def async_play_media(self, url: str, title: str = "Home Assistant", artist: str = "Media Player") -> None:
        """Stream an audio URL directly to the soundbar."""
        play_req = {
            "add": False,
            "position": 0,
            "sync": False,
            "time": 0,
            "item": {
                "title": title,
                "artist": artist,
                "uri": url,
                "albumart": "",
                "objID": "",
                "source": 0,
                "duration": 0,
                "albumtitle": "",
                "cptype": 0
            }
        }
        await self.async_send_command("LOCAL_PLAY_URL", play_req)

    async def async_media_play(self) -> None:
        """Resume playback."""
        await self.async_send_command("PLAY_CMD", {"playctrl": PLAY_CTRL_PLAY, "repeat": 0, "shuffle": False})

    async def async_media_pause(self) -> None:
        """Pause playback."""
        await self.async_send_command("PLAY_CMD", {"playctrl": PLAY_CTRL_PAUSE, "repeat": 0, "shuffle": False})

    async def async_media_stop(self) -> None:
        """Stop playback."""
        await self.async_send_command("PLAY_CMD", {"playctrl": PLAY_CTRL_STOP, "repeat": 0, "shuffle": False})

    async def async_set_name(self, name: str) -> Dict[str, Any]:
        """Set / rename the speaker petname."""
        return await self.async_send_command("SPK_INFO_MODIFY", {"name": name})

    async def async_share_home_info(self, ssid: str, password: str, auth_type: int = 0) -> Dict[str, Any]:
        """Send Wi-Fi credentials to soundbar for initial provisioning or network switch."""
        return await self.async_send_command("SHARE_HOME_INFO", {
            "ssid": ssid,
            "pwd": password,
            "auth": auth_type,
        })
