"""Tests for the LG Music Flow DataUpdateCoordinator."""

from __future__ import annotations

from datetime import timedelta
import sys
import types
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

core_mod = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))
core_mod.HomeAssistant = object
homeassistant.core = core_mod

helpers_mod = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
helpers_mod.__path__ = []

update_coord_mod = sys.modules.setdefault(
    "homeassistant.helpers.update_coordinator",
    types.ModuleType("homeassistant.helpers.update_coordinator"),
)


class DataUpdateCoordinator:
    """Minimal stub for DataUpdateCoordinator."""

    def __init__(self, hass, logger, *, name, update_interval) -> None:
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval


class UpdateFailed(Exception):
    """Stub for UpdateFailed."""


update_coord_mod.DataUpdateCoordinator = DataUpdateCoordinator
update_coord_mod.UpdateFailed = UpdateFailed
helpers_mod.update_coordinator = update_coord_mod

from custom_components.lg_musicflow.client import LGMusicFlowError
from custom_components.lg_musicflow.const import (
    CONF_PAUSE_STANDBY_POLLING,
    CONF_SCAN_INTERVAL,
    STATE_PLAYING,
)
from custom_components.lg_musicflow.coordinator import LGMusicFlowCoordinator


class FakeClient:
    """Fake client returning controlled status payloads."""

    def __init__(self, status: dict | None = None) -> None:
        self.host = "10.0.2.154"
        self.status = status or {}
        self.should_raise: Exception | None = None

    async def async_get_status(self) -> dict:
        if self.should_raise:
            raise self.should_raise
        return self.status


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    """Test coordinator scan intervals and standby pause."""

    async def test_default_intervals(self) -> None:
        client = FakeClient()
        coord = LGMusicFlowCoordinator(None, client, {}, entry=None)
        self.assertEqual(coord.normal_interval, timedelta(seconds=6))
        self.assertEqual(coord.fast_interval, timedelta(seconds=3))
        self.assertEqual(coord.standby_interval, timedelta(seconds=30))
        self.assertFalse(coord.pause_standby)
        self.assertEqual(coord.update_interval, timedelta(seconds=6))

    async def test_options_custom_interval(self) -> None:
        client = FakeClient()
        entry = types.SimpleNamespace(
            options={CONF_SCAN_INTERVAL: 15, CONF_PAUSE_STANDBY_POLLING: True}
        )
        coord = LGMusicFlowCoordinator(None, client, {}, entry=entry)
        self.assertEqual(coord.normal_interval, timedelta(seconds=15))
        self.assertEqual(coord.fast_interval, timedelta(seconds=3))
        self.assertEqual(coord.standby_interval, timedelta(seconds=30))
        self.assertTrue(coord.pause_standby)

    async def test_playing_switches_to_fast_interval(self) -> None:
        client = FakeClient({"play": {"playing": STATE_PLAYING}, "func": {"connect": 1}})
        coord = LGMusicFlowCoordinator(None, client, {}, entry=None)
        await coord._async_update_data()
        self.assertEqual(coord.update_interval, timedelta(seconds=3))

    async def test_standby_backs_off_interval_by_default(self) -> None:
        client = FakeClient({"play": {"playing": -1}, "func": {"type": 0, "connect": 0}})
        coord = LGMusicFlowCoordinator(None, client, {}, entry=None)
        await coord._async_update_data()
        self.assertEqual(coord.update_interval, timedelta(seconds=30))

    async def test_standby_pauses_polling_when_option_enabled(self) -> None:
        client = FakeClient({"play": {"playing": -1}, "func": {"type": 0, "connect": 0}})
        entry = types.SimpleNamespace(options={CONF_PAUSE_STANDBY_POLLING: True})
        coord = LGMusicFlowCoordinator(None, client, {}, entry=entry)
        await coord._async_update_data()
        self.assertIsNone(coord.update_interval)

    async def test_wake_from_standby_restores_normal_interval(self) -> None:
        client = FakeClient({"play": {"playing": -1}, "func": {"type": 0, "connect": 0}})
        entry = types.SimpleNamespace(options={CONF_PAUSE_STANDBY_POLLING: True})
        coord = LGMusicFlowCoordinator(None, client, {}, entry=entry)
        await coord._async_update_data()
        self.assertIsNone(coord.update_interval)

        # Speaker is turned on via HDMI ARC
        client.status = {"play": {"playing": -1}, "func": {"type": 4, "connect": 1}}
        await coord._async_update_data()
        self.assertEqual(coord.update_interval, timedelta(seconds=6))

    async def test_error_with_pause_standby_sets_interval_none(self) -> None:
        client = FakeClient()
        client.should_raise = LGMusicFlowError("Connection dropped in standby")
        entry = types.SimpleNamespace(options={CONF_PAUSE_STANDBY_POLLING: True})
        coord = LGMusicFlowCoordinator(None, client, {}, entry=entry)

        with self.assertRaises(UpdateFailed):
            await coord._async_update_data()
        self.assertIsNone(coord.update_interval)


    async def test_physical_input_with_connect_zero_keeps_normal_interval(self) -> None:
        client = FakeClient({"play": {"playing": -1}, "func": {"type": 7, "connect": 0}})
        coord = LGMusicFlowCoordinator(None, client, {}, entry=None)
        await coord._async_update_data()
        self.assertEqual(coord.update_interval, timedelta(seconds=6))

if __name__ == "__main__":
    unittest.main()
