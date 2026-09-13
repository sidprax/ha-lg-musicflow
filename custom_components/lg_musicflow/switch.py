"""Switch platform for LG MusicFlow (Legacy)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LGMusicFlowCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the LG Music Flow switches."""
    coordinator: LGMusicFlowCoordinator = hass.data[DOMAIN][entry.entry_id]
    switches: list[SwitchEntity] = []

    settings = coordinator.data.get("settings", {})
    if "nightmode" in settings:
        switches.append(LGMusicFlowNightModeSwitch(coordinator, entry))
    if "autopower" in settings:
        switches.append(LGMusicFlowAutoPowerSwitch(coordinator, entry))

    async_add_entities(switches)


class LGMusicFlowBaseSwitch(CoordinatorEntity[LGMusicFlowCoordinator], SwitchEntity):
    """Base switch for LG Music Flow speaker features."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LGMusicFlowCoordinator, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        info = coordinator.product_info.get("info", {})
        self._mac = info.get("wirelessmac") or info.get("btmac") or entry.data["host"]
        self._model = coordinator.product_info.get("modelname", "Music Flow")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            name=self._entry.data.get(CONF_NAME, f"LG {self._model}"),
            manufacturer="LG Electronics",
            model=self._model,
        )


class LGMusicFlowNightModeSwitch(LGMusicFlowBaseSwitch):
    """Night mode switch."""

    _attr_name = "Night Mode"
    _attr_icon = "mdi:weather-night"

    def __init__(self, coordinator: LGMusicFlowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._mac}_night_mode"

    @property
    def is_on(self) -> bool:
        """Return true if night mode is on."""
        return self.coordinator.data.get("settings", {}).get("nightmode", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on night mode."""
        await self.coordinator.client.async_set_night_mode(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off night mode."""
        await self.coordinator.client.async_set_night_mode(False)
        await self.coordinator.async_request_refresh()


class LGMusicFlowAutoPowerSwitch(LGMusicFlowBaseSwitch):
    """Auto power switch (automatic optical/input change)."""

    _attr_name = "Auto Power"
    _attr_icon = "mdi:power-cycle"

    def __init__(self, coordinator: LGMusicFlowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._mac}_auto_power"

    @property
    def is_on(self) -> bool:
        """Return true if auto power is on."""
        return self.coordinator.data.get("settings", {}).get("autopower", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on auto power."""
        await self.coordinator.client.async_set_auto_power(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off auto power."""
        await self.coordinator.client.async_set_auto_power(False)
        await self.coordinator.async_request_refresh()
