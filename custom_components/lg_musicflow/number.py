"""Number platform for LG MusicFlow (Legacy)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    """Set up the LG Music Flow number entities."""
    coordinator: LGMusicFlowCoordinator = hass.data[DOMAIN][entry.entry_id]
    settings = coordinator.data.get("settings", {})

    if "wooferlevel" in settings:
        async_add_entities([LGMusicFlowWooferNumber(coordinator, entry)])


class LGMusicFlowWooferNumber(CoordinatorEntity[LGMusicFlowCoordinator], NumberEntity):
    """Representation of the subwoofer level control."""

    _attr_has_entity_name = True
    _attr_name = "Subwoofer Level"
    _attr_icon = "mdi:speaker-wireless"
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = "dB"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: LGMusicFlowCoordinator, entry: ConfigEntry) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._entry = entry
        info = coordinator.product_info.get("info", {})
        self._mac = info.get("wirelessmac") or info.get("btmac") or entry.data["host"]
        self._model = coordinator.product_info.get("modelname", "Music Flow")
        self._attr_unique_id = f"{self._mac}_subwoofer_level"

        # Calculate bounds from speaker settings
        settings = coordinator.data.get("settings", {})
        self._offset = abs(settings.get("wooferoffset", -15))
        max_progress = settings.get("woofermax", 21)
        self._attr_native_min_value = float(-self._offset)
        self._attr_native_max_value = float(max_progress - self._offset)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            name=self._entry.data.get(CONF_NAME, f"LG {self._model}"),
            manufacturer="LG Electronics",
            model=self._model,
        )

    @property
    def native_value(self) -> float | None:
        """Return current woofer level in dB."""
        raw_level = self.coordinator.data.get("settings", {}).get("wooferlevel")
        if raw_level is not None:
            return float(raw_level - self._offset)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the woofer level."""
        raw_progress = int(round(value + self._offset))
        await self.coordinator.client.async_set_woofer_level(raw_progress)
        await self.coordinator.async_request_refresh()
