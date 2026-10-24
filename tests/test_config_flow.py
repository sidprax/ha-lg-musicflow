"""Tests for the LG Music Flow config flow."""

from __future__ import annotations

import importlib
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
lg_musicflow = sys.modules.setdefault(
    "custom_components.lg_musicflow", types.ModuleType("custom_components.lg_musicflow")
)
lg_musicflow.__path__ = [str(INTEGRATION)]

# Minimal Home Assistant and Voluptuous stubs for standalone config_flow testing.
if "voluptuous" not in sys.modules:
    vol = types.ModuleType("voluptuous")
    vol.Schema = lambda schema: schema
    vol.Required = lambda key, **kwargs: key
    vol.Optional = lambda key, **kwargs: key
    vol.All = lambda *args: args[0]
    vol.Coerce = lambda t: t
    vol.Range = lambda **kwargs: kwargs
    sys.modules["voluptuous"] = vol

homeassistant = sys.modules.setdefault(
    "homeassistant", types.ModuleType("homeassistant")
)
homeassistant.__path__ = []
core_mod = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))
core_mod.callback = lambda f: f
homeassistant.core = core_mod


class AbortFlow(Exception):
    """Stub for homeassistant.data_entry_flow.AbortFlow."""

    def __init__(self, reason: str, description_placeholders: dict | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.description_placeholders = description_placeholders


class BaseConfigFlow:
    """Stub for homeassistant.config_entries.ConfigFlow."""

    def __init_subclass__(cls, **kwargs):
        return super().__init_subclass__()

    def __init__(self) -> None:
        self.context: dict = {}
        self._unique_id: str | None = None
        self._already_configured = False
        self.last_updates: dict | None = None

    async def async_set_unique_id(self, unique_id: str) -> None:
        self._unique_id = unique_id

    def _abort_if_unique_id_configured(self, updates: dict | None = None) -> None:
        self.last_updates = updates
        if self._already_configured:
            raise AbortFlow("already_configured")

    def async_create_entry(self, *, title: str, data: dict) -> dict:
        return {"type": "create_entry", "title": title, "data": data}

    def async_abort(self, *, reason: str) -> dict:
        return {"type": "abort", "reason": reason}

    def async_show_form(self, *, step_id: str, data_schema=None, errors=None, description_placeholders=None) -> dict:
        return {
            "type": "form",
            "step_id": step_id,
            "errors": errors or {},
            "description_placeholders": description_placeholders,
        }

    def async_show_menu(self, *, step_id: str, menu_options: list[str]) -> dict:
        return {"type": "menu", "step_id": step_id, "menu_options": menu_options}


class BaseOptionsFlow:
    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    def async_create_entry(self, *, title: str, data: dict) -> dict:
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, *, step_id: str, data_schema=None, errors=None, description_placeholders=None) -> dict:
        return {"type": "form", "step_id": step_id, "data_schema": data_schema, "errors": errors or {}}

config_entries_mod = types.ModuleType("homeassistant.config_entries")
config_entries_mod.ConfigFlow = BaseConfigFlow
config_entries_mod.OptionsFlow = BaseOptionsFlow
sys.modules["homeassistant.config_entries"] = config_entries_mod
homeassistant.config_entries = config_entries_mod

const_mod = types.ModuleType("homeassistant.const")
const_mod.CONF_HOST = "host"
const_mod.CONF_NAME = "name"
const_mod.CONF_PORT = "port"
sys.modules["homeassistant.const"] = const_mod

data_entry_flow_mod = types.ModuleType("homeassistant.data_entry_flow")
data_entry_flow_mod.FlowResult = dict
data_entry_flow_mod.AbortFlow = AbortFlow
sys.modules["homeassistant.data_entry_flow"] = data_entry_flow_mod

helpers_mod = sys.modules.setdefault(
    "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
)
helpers_mod.__path__ = []
service_info_mod = types.ModuleType("homeassistant.helpers.service_info")
service_info_mod.__path__ = []
sys.modules["homeassistant.helpers.service_info"] = service_info_mod


class SsdpServiceInfo:
    """Stub for SsdpServiceInfo."""

    def __init__(self, ssdp_location: str) -> None:
        self.ssdp_location = ssdp_location


ssdp_mod = types.ModuleType("homeassistant.helpers.service_info.ssdp")
ssdp_mod.SsdpServiceInfo = SsdpServiceInfo
sys.modules["homeassistant.helpers.service_info.ssdp"] = ssdp_mod

config_flow_module = importlib.import_module("custom_components.lg_musicflow.config_flow")
LGMusicFlowConfigFlow = config_flow_module.LGMusicFlowConfigFlow


class FakeClient:
    """Fake LGMusicFlowClient for config flow testing."""

    instances: list[FakeClient] = []
    raise_on_product_info: Exception | None = None

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.closed = False
        FakeClient.instances.append(self)

    async def async_get_product_info(self) -> dict:
        if FakeClient.raise_on_product_info is not None:
            raise FakeClient.raise_on_product_info
        return {
            "modelname": "SJ9",
            "info": {
                "wirelessmac": "AA:BB:CC:DD:EE:FF",
                "name": "DarkBar",
            },
        }

    async def async_set_name(self, name: str) -> None:
        return None

    async def async_share_home_info(self, ssid: str, pwd: str) -> None:
        return None

    async def async_close(self) -> None:
        self.closed = True


class ConfigFlowAbortTests(unittest.IsolatedAsyncioTestCase):
    """Verify AbortFlow from _abort_if_unique_id_configured is not swallowed."""

    def setUp(self) -> None:
        FakeClient.instances.clear()
        FakeClient.raise_on_product_info = None
        self._orig_client = config_flow_module.LGMusicFlowClient
        config_flow_module.LGMusicFlowClient = FakeClient
        self.addCleanup(
            setattr,
            config_flow_module,
            "LGMusicFlowClient",
            self._orig_client,
        )

    async def test_connect_propagates_abort_flow_and_closes_client(self) -> None:
        flow = LGMusicFlowConfigFlow()
        flow._already_configured = True

        with self.assertRaises(AbortFlow) as ctx:
            await flow.async_step_connect({"host": "10.0.2.99", "port": 9741})

        self.assertEqual(ctx.exception.reason, "already_configured")
        self.assertEqual(flow.last_updates, {"host": "10.0.2.99"})
        self.assertEqual(len(FakeClient.instances), 1)
        self.assertTrue(FakeClient.instances[0].closed)

    async def test_wizard_ethernet_propagates_abort_flow_and_closes_client(self) -> None:
        flow = LGMusicFlowConfigFlow()
        flow._already_configured = True

        with self.assertRaises(AbortFlow) as ctx:
            await flow.async_step_wizard_ethernet(
                {
                    "speaker_host": "10.0.2.99",
                    "wifi_ssid": "MyWiFi",
                    "wifi_password": "secret",
                    "speaker_name": "DarkBar",
                }
            )

        self.assertEqual(ctx.exception.reason, "already_configured")
        self.assertEqual(flow.last_updates, {"host": "10.0.2.99"})
        self.assertEqual(len(FakeClient.instances), 1)
        self.assertTrue(FakeClient.instances[0].closed)

    async def test_ssdp_propagates_abort_flow_and_closes_client(self) -> None:
        flow = LGMusicFlowConfigFlow()
        flow._already_configured = True

        with self.assertRaises(AbortFlow) as ctx:
            await flow.async_step_ssdp(
                SsdpServiceInfo("http://10.0.2.99:1818/description.xml")
            )

        self.assertEqual(ctx.exception.reason, "already_configured")
        self.assertEqual(flow.last_updates, {"host": "10.0.2.99"})
        self.assertEqual(len(FakeClient.instances), 1)
        self.assertTrue(FakeClient.instances[0].closed)


    async def test_options_flow_init_shows_form(self) -> None:
        entry = types.SimpleNamespace(options={})
        options_flow = LGMusicFlowConfigFlow.async_get_options_flow(entry)
        result = await options_flow.async_step_init()
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "init")

    async def test_options_flow_init_updates_options(self) -> None:
        entry = types.SimpleNamespace(options={"scan_interval": 6})
        options_flow = LGMusicFlowConfigFlow.async_get_options_flow(entry)
        result = await options_flow.async_step_init({"scan_interval": 15, "pause_standby_polling": True})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"], {"scan_interval": 15, "pause_standby_polling": True})

if __name__ == "__main__":
    unittest.main()
