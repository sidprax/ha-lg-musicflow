"""Config flow for LG MusicFlow (Legacy) integration."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo

from .client import LGMusicFlowClient, LGMusicFlowError
from .const import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class LGMusicFlowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LG Music Flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None
        self._discovered_model: str | None = None
        self._discovered_mac: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - choice between manual IP connection and guided setup wizard."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["connect", "wizard_menu"],
        )

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual IP connection to an existing speaker."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            client = LGMusicFlowClient(host, port)

            try:
                prod = await client.async_get_product_info()
                info = prod.get("info", {})
                mac = info.get("wirelessmac") or info.get("btmac") or host
                name = info.get("name") or prod.get("petname") or f"LG Speaker ({host})"

                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})

                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_NAME: name,
                    },
                )
            except LGMusicFlowError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error connecting to LG Music Flow device")
                errors["base"] = "unknown"
            finally:
                await client.async_close()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )
        return self.async_show_form(
            step_id="connect", data_schema=schema, errors=errors
        )

    async def async_step_wizard_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Menu to choose between Ethernet setup (inside HA) or Hotspot setup (from PC)."""
        return self.async_show_menu(
            step_id="wizard_menu",
            menu_options=["wizard_ethernet", "wizard_hotspot_guide"],
        )

    async def async_step_wizard_ethernet(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Guide and credentials form for Ethernet-assisted Wi-Fi setup inside Home Assistant."""
        errors = {}

        if user_input is not None:
            host = user_input["speaker_host"]
            ssid = user_input["wifi_ssid"]
            pwd = user_input.get("wifi_password", "")
            spk_name = user_input.get("speaker_name")

            client = LGMusicFlowClient(host, DEFAULT_PORT)
            try:
                if spk_name:
                    await client.async_set_name(spk_name)
                await client.async_share_home_info(ssid, pwd)

                # Try to fetch device info and add directly to HA
                try:
                    prod = await client.async_get_product_info()
                    info = prod.get("info", {})
                    mac = info.get("wirelessmac") or info.get("btmac") or host
                    name = (
                        spk_name
                        or info.get("name")
                        or prod.get("petname")
                        or f"LG Speaker ({host})"
                    )
                    await self.async_set_unique_id(mac)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                    return self.async_create_entry(
                        title=name,
                        data={
                            CONF_HOST: host,
                            CONF_PORT: DEFAULT_PORT,
                            CONF_NAME: name,
                        },
                    )
                except Exception:  # noqa: BLE001
                    return self.async_abort(reason="provision_success")

            except LGMusicFlowError:
                errors["base"] = "cannot_connect_speaker"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Error provisioning LG speaker Wi-Fi")
                errors["base"] = "unknown"
            finally:
                await client.async_close()

        schema = vol.Schema(
            {
                vol.Required("speaker_host"): str,
                vol.Required("wifi_ssid"): str,
                vol.Optional("wifi_password", default=""): str,
                vol.Optional("speaker_name"): str,
            }
        )
        return self.async_show_form(
            step_id="wizard_ethernet", data_schema=schema, errors=errors
        )

    async def async_step_wizard_hotspot_guide(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Display step-by-step instructions for PC/laptop hotspot setup."""
        if user_input is not None:
            return self.async_abort(reason="hotspot_guide_complete")

        return self.async_show_form(step_id="wizard_hotspot_guide")

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo) -> FlowResult:
        """Handle SSDP discovery."""
        location = discovery_info.ssdp_location or ""
        parsed = urlparse(location)
        host = parsed.hostname

        if not host:
            return self.async_abort(reason="cannot_connect")

        client = LGMusicFlowClient(host, DEFAULT_PORT)
        try:
            prod = await client.async_get_product_info()
            info = prod.get("info", {})
            mac = info.get("wirelessmac") or info.get("btmac") or host
            self._discovered_name = (
                info.get("name") or prod.get("petname") or f"LG Speaker ({host})"
            )
            self._discovered_model = prod.get("modelname", "Music Flow")
            self._discovered_host = host
            self._discovered_mac = mac

            await self.async_set_unique_id(mac)
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        except Exception:  # noqa: BLE001
            return self.async_abort(reason="cannot_connect")
        finally:
            await client.async_close()

        self.context["title_placeholders"] = {
            "name": self._discovered_name,
            "model": self._discovered_model,
            "host": self._discovered_host,
        }
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered_name or f"LG {self._discovered_model}",
                data={
                    CONF_HOST: self._discovered_host,
                    CONF_PORT: DEFAULT_PORT,
                    CONF_NAME: self._discovered_name,
                },
            )

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._discovered_name,
                "model": self._discovered_model,
                "host": self._discovered_host,
            },
        )
