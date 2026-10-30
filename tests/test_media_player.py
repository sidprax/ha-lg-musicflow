"""Tests for LG Music Flow media player platform."""

from __future__ import annotations

import sys
import types
from typing import Generic, TypeVar
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COMPONENTS = ROOT / "custom_components"
INTEGRATION = CUSTOM_COMPONENTS / "lg_musicflow"

custom_components = sys.modules.setdefault(
    "custom_components", types.ModuleType("custom_components")
)
custom_components.__path__ = [str(CUSTOM_COMPONENTS)]

homeassistant = sys.modules.setdefault(
    "homeassistant", types.ModuleType("homeassistant")
)
homeassistant.__path__ = []

components_mod = sys.modules.setdefault(
    "homeassistant.components", types.ModuleType("homeassistant.components")
)
components_mod.__path__ = []

media_player_mod = types.ModuleType("homeassistant.components.media_player")


class MediaPlayerDeviceClass:
    SPEAKER = "speaker"


class MediaPlayerState:
    PLAYING = "playing"
    PAUSED = "paused"
    BUFFERING = "buffering"
    ON = "on"
    OFF = "off"
    IDLE = "idle"
    STANDBY = "standby"


class MediaPlayerEntityFeature:
    VOLUME_SET = 1
    VOLUME_MUTE = 2
    VOLUME_STEP = 4
    SELECT_SOURCE = 8
    SELECT_SOUND_MODE = 16
    PLAY_MEDIA = 32
    PLAY = 64
    PAUSE = 128
    STOP = 256
    MEDIA_ANNOUNCE = 512
    BROWSE_MEDIA = 1024
    TURN_OFF = 2048
    TURN_ON = 4096


media_player_mod.MediaPlayerDeviceClass = MediaPlayerDeviceClass
media_player_mod.MediaPlayerState = MediaPlayerState
media_player_mod.MediaPlayerEntityFeature = MediaPlayerEntityFeature
media_player_mod.MediaPlayerEntity = object
media_player_mod.MediaType = object
media_player_mod.async_process_play_media_url = lambda hass, url: url
sys.modules["homeassistant.components.media_player"] = media_player_mod

media_source_mod = types.ModuleType("homeassistant.components.media_source")
media_source_mod.is_media_source_id = lambda media_id: False
sys.modules["homeassistant.components.media_source"] = media_source_mod

exceptions_mod = sys.modules.setdefault(
    "homeassistant.exceptions", types.ModuleType("homeassistant.exceptions")
)
exceptions_mod.HomeAssistantError = Exception

helpers_mod = sys.modules.setdefault(
    "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
)
helpers_mod.__path__ = []

device_reg_mod = types.ModuleType("homeassistant.helpers.device_registry")
device_reg_mod.DeviceInfo = dict
sys.modules["homeassistant.helpers.device_registry"] = device_reg_mod

entity_plat_mod = types.ModuleType("homeassistant.helpers.entity_platform")
entity_plat_mod.AddEntitiesCallback = object
sys.modules["homeassistant.helpers.entity_platform"] = entity_plat_mod

update_coord_mod = sys.modules.setdefault(
    "homeassistant.helpers.update_coordinator",
    types.ModuleType("homeassistant.helpers.update_coordinator"),
)

_T = TypeVar("_T")


class CoordinatorEntity(Generic[_T]):
    def __init__(self, coordinator: _T) -> None:
        self.coordinator = coordinator


update_coord_mod.CoordinatorEntity = CoordinatorEntity

core_mod = sys.modules.setdefault(
    "homeassistant.core", types.ModuleType("homeassistant.core")
)
core_mod.HomeAssistant = object

const_mod = sys.modules.setdefault(
    "homeassistant.const", types.ModuleType("homeassistant.const")
)
const_mod.CONF_HOST = "host"
const_mod.CONF_NAME = "name"

from custom_components.lg_musicflow.client import LGMusicFlowError
from custom_components.lg_musicflow.const import (
    DATA_STREAM_MANAGER,
    DOMAIN,
    STATE_PLAYING,
)
from custom_components.lg_musicflow.media_player import LGMusicFlowMediaPlayer


class FakeClient:
    def __init__(self) -> None:
        self.power_off_called = False
        self.function_set: int | None = None
        self.sound_mode_set: int | None = None
        self.closed = False

    async def async_power_off(self) -> None:
        self.power_off_called = True

    async def async_set_function(self, fn: int) -> None:
        self.function_set = fn

    async def async_set_sound_mode(self, mode: int) -> None:
        self.sound_mode_set = mode

    async def async_media_stop(self) -> None:
        pass

    async def async_close(self) -> None:
        self.closed = True


class FakeCoordinator:
    def __init__(self, data: dict | None = None) -> None:
        self.data = data or {}
        self.product_info = {
            "modelname": "SJ9",
            "info": {
                "wirelessmac": "00:11:22:33:44:55",
                "functionlist": [0, 4, 7],
                "eqlist": [0, 7, 13, 14, 15],
            },
        }
        self.client = FakeClient()
        self.hass = types.SimpleNamespace(
            data={DOMAIN: {DATA_STREAM_MANAGER: FakeStreamManager()}}
        )
        self.refreshed = False
        self.pause_standby = True
        self.update_interval = None

    async def async_request_refresh(self) -> None:
        self.refreshed = True


class FakeStreamManager:
    async def async_release(self, stream_id: str | None) -> None:
        pass


class MediaPlayerStateTests(unittest.IsolatedAsyncioTestCase):
    """Test media player states and power off actions."""

    def test_state_playing(self) -> None:
        coord = FakeCoordinator({"play": {"playing": STATE_PLAYING}, "func": {"type": 0, "connect": 1}})
        entry = types.SimpleNamespace(data={"host": "10.0.2.154"})
        player = LGMusicFlowMediaPlayer(coord, entry)
        self.assertEqual(player.state, MediaPlayerState.PLAYING)

    def test_state_on_when_optical_and_connected(self) -> None:
        coord = FakeCoordinator({"play": {"playing": -1}, "func": {"type": 4, "connect": 1}})
        entry = types.SimpleNamespace(data={"host": "10.0.2.154"})
        player = LGMusicFlowMediaPlayer(coord, entry)
        self.assertEqual(player.state, MediaPlayerState.ON)

    def test_state_standby_when_optical_arc_with_connect_zero(self) -> None:
        coord = FakeCoordinator({"play": {"playing": -1}, "func": {"type": 7, "connect": 0}})
        entry = types.SimpleNamespace(data={"host": "10.0.2.154"})
        player = LGMusicFlowMediaPlayer(coord, entry)
        self.assertEqual(player.state, MediaPlayerState.STANDBY)

    def test_state_idle_when_wifi_and_connect_zero(self) -> None:
        coord = FakeCoordinator({"play": {"playing": -1}, "func": {"type": 0, "connect": 0}})
        entry = types.SimpleNamespace(data={"host": "10.0.2.154"})
        player = LGMusicFlowMediaPlayer(coord, entry)
        self.assertEqual(player.state, MediaPlayerState.IDLE)

    async def test_async_turn_off_sets_standby_state(self) -> None:
        coord = FakeCoordinator({"play": {"playing": -1}, "func": {"type": 4, "connect": 1}})
        entry = types.SimpleNamespace(data={"host": "10.0.2.154"})
        player = LGMusicFlowMediaPlayer(coord, entry)
        self.assertEqual(player.state, MediaPlayerState.ON)

        await player.async_turn_off()
        self.assertEqual(player.state, MediaPlayerState.STANDBY)
        self.assertTrue(coord.client.power_off_called)
        self.assertTrue(coord.refreshed)

    async def test_async_turn_on_resets_standby_state(self) -> None:
        coord = FakeCoordinator({"play": {"playing": -1}, "func": {"type": 4, "connect": 1}})
        entry = types.SimpleNamespace(data={"host": "10.0.2.154"})
        player = LGMusicFlowMediaPlayer(coord, entry)

        await player.async_turn_off()
        self.assertEqual(player.state, MediaPlayerState.STANDBY)

        await player.async_turn_on()
        self.assertEqual(player.state, MediaPlayerState.ON)
        self.assertTrue(coord.refreshed)

    async def test_async_turn_on_preserves_physical_input(self) -> None:
        coord = FakeCoordinator({"play": {"playing": -1}, "func": {"type": 4, "connect": 1}})
        entry = types.SimpleNamespace(data={"host": "10.0.2.154"})
        player = LGMusicFlowMediaPlayer(coord, entry)

        await player.async_turn_on()
        self.assertIsNone(coord.client.function_set)
        self.assertTrue(coord.refreshed)

    async def test_async_turn_on_sets_wifi_when_already_on_wifi(self) -> None:
        coord = FakeCoordinator({"play": {"playing": -1}, "func": {"type": 0, "connect": 0}})
        entry = types.SimpleNamespace(data={"host": "10.0.2.154"})
        player = LGMusicFlowMediaPlayer(coord, entry)

        await player.async_turn_on()
        self.assertEqual(coord.client.function_set, 0)
        self.assertTrue(coord.refreshed)

    def test_state_idle_when_connected_wifi_not_playing(self) -> None:
        coord = FakeCoordinator({"play": {"playing": -1}, "func": {"type": 0, "connect": 1}})
        entry = types.SimpleNamespace(data={"host": "10.0.2.154"})
        player = LGMusicFlowMediaPlayer(coord, entry)
        self.assertEqual(player.state, MediaPlayerState.IDLE)

    async def test_async_turn_off_does_not_force_wifi_on_power_off_error(self) -> None:
        coord = FakeCoordinator({"play": {"playing": -1}, "func": {"type": 4, "connect": 1}})
        entry = types.SimpleNamespace(data={"host": "10.0.2.154"})
        player = LGMusicFlowMediaPlayer(coord, entry)

        async def failing_power_off():
            raise LGMusicFlowError("parsing error")

        coord.client.async_power_off = failing_power_off
        await player.async_turn_off()
        self.assertIsNone(coord.client.function_set)
        self.assertTrue(coord.refreshed)

    async def test_async_select_sound_mode(self) -> None:
        coord = FakeCoordinator({"eq": {"currenteq": 14}, "func": {"type": 4, "connect": 1}})
        entry = types.SimpleNamespace(data={"host": "10.0.2.154"})
        player = LGMusicFlowMediaPlayer(coord, entry)

        await player.async_select_sound_mode("Movie")
        self.assertEqual(coord.client.sound_mode_set, 13)
        self.assertTrue(coord.refreshed)


if __name__ == "__main__":
    unittest.main()
