"""The LG MusicFlow (Legacy) integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .client import LGMusicFlowClient
from .const import DATA_STREAM_MANAGER, DEFAULT_PORT, DOMAIN
from .coordinator import LGMusicFlowCoordinator
from .stream import LGMusicFlowStreamManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LG Music Flow from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    client = LGMusicFlowClient(host, port)
    try:
        product_info = await client.async_get_product_info()

        coordinator = LGMusicFlowCoordinator(hass, client, product_info)
        await coordinator.async_config_entry_first_refresh()

        domain_data = hass.data.setdefault(DOMAIN, {})
        stream_manager = domain_data.get(DATA_STREAM_MANAGER)
        if stream_manager is None:
            stream_manager = LGMusicFlowStreamManager(hass)
            await stream_manager.async_start()
            domain_data[DATA_STREAM_MANAGER] = stream_manager
        domain_data[entry.entry_id] = coordinator
    except Exception:
        await client.async_close()
        raise

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an LG Music Flow config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data[DOMAIN]
        coordinator: LGMusicFlowCoordinator = domain_data.pop(entry.entry_id)
        await coordinator.client.async_close()
        if not any(not key.startswith("_") for key in domain_data):
            stream_manager: LGMusicFlowStreamManager = domain_data.pop(
                DATA_STREAM_MANAGER
            )
            await stream_manager.async_stop()
            hass.data.pop(DOMAIN)
    return unload_ok
