"""Tests for the LG Music Flow component setup."""

from __future__ import annotations

import importlib.util
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

core_mod = types.ModuleType("homeassistant.core")
core_mod.HomeAssistant = object
sys.modules["homeassistant.core"] = core_mod
homeassistant.core = core_mod


class ConfigEntryNotReady(Exception):
    """Stub for homeassistant.exceptions.ConfigEntryNotReady."""


exceptions_mod = types.ModuleType("homeassistant.exceptions")
exceptions_mod.ConfigEntryNotReady = ConfigEntryNotReady
sys.modules["homeassistant.exceptions"] = exceptions_mod
homeassistant.exceptions = exceptions_mod

helpers_mod = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
helpers_mod.__path__ = []

update_coord_mod = types.ModuleType("homeassistant.helpers.update_coordinator")
update_coord_mod.DataUpdateCoordinator = object
update_coord_mod.UpdateFailed = Exception
sys.modules["homeassistant.helpers.update_coordinator"] = update_coord_mod
helpers_mod.update_coordinator = update_coord_mod

aiohttp_client_mod = types.ModuleType("homeassistant.helpers.aiohttp_client")
aiohttp_client_mod.async_get_clientsession = lambda hass: None
sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client_mod
helpers_mod.aiohttp_client = aiohttp_client_mod

const_mod = sys.modules.setdefault("homeassistant.const", types.ModuleType("homeassistant.const"))
const_mod.CONF_HOST = "host"
const_mod.CONF_PORT = "port"


class Platform:
    MEDIA_PLAYER = "media_player"
    SWITCH = "switch"
    NUMBER = "number"
    SELECT = "select"


const_mod.Platform = Platform

config_entries_mod = sys.modules.setdefault(
    "homeassistant.config_entries", types.ModuleType("homeassistant.config_entries")
)


class ConfigEntry:
    def __init__(self, entry_id: str, data: dict, options: dict | None = None) -> None:
        self.entry_id = entry_id
        self.data = data
        self.options = options or {}

    def async_on_unload(self, callback) -> None:
        pass

    def add_update_listener(self, listener):
        return listener


config_entries_mod.ConfigEntry = ConfigEntry

# Load __init__.py as custom_components.lg_musicflow
spec = importlib.util.spec_from_file_location(
    "custom_components.lg_musicflow",
    str(INTEGRATION / "__init__.py"),
    submodule_search_locations=[str(INTEGRATION)],
)
init_module = importlib.util.module_from_spec(spec)
sys.modules["custom_components.lg_musicflow"] = init_module
spec.loader.exec_module(init_module)

client_module = sys.modules["custom_components.lg_musicflow.client"]
LGMusicFlowError = client_module.LGMusicFlowError


class FakeClient:
    instances: list[FakeClient] = []

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.closed = False
        FakeClient.instances.append(self)

    async def async_get_product_info(self) -> dict:
        raise LGMusicFlowError("Connection refused")

    async def async_close(self) -> None:
        self.closed = True


class SetupEntryTests(unittest.IsolatedAsyncioTestCase):
    """Test async_setup_entry error handling and lifecycle."""

    def setUp(self) -> None:
        FakeClient.instances.clear()
        self._orig_client = init_module.LGMusicFlowClient
        init_module.LGMusicFlowClient = FakeClient
        self.addCleanup(
            setattr,
            init_module,
            "LGMusicFlowClient",
            self._orig_client,
        )

    async def test_setup_entry_raises_config_entry_not_ready_on_offline_speaker(self) -> None:
        hass = types.SimpleNamespace(data={})
        entry = ConfigEntry("test_id", {"host": "10.0.2.99", "port": 9741})

        with self.assertRaises(ConfigEntryNotReady):
            await init_module.async_setup_entry(hass, entry)

        self.assertEqual(len(FakeClient.instances), 1)
        self.assertTrue(FakeClient.instances[0].closed)


    async def test_update_listener_reloads_entry(self) -> None:
        reloaded = []
        async def fake_reload(entry_id: str) -> None:
            reloaded.append(entry_id)

        hass = types.SimpleNamespace(
            config_entries=types.SimpleNamespace(
                async_reload=fake_reload
            )
        )
        entry = ConfigEntry("test_id", {"host": "10.0.2.99", "port": 9741})
        await init_module.update_listener(hass, entry)
        self.assertEqual(reloaded, ["test_id"])

if __name__ == "__main__":
    unittest.main()
