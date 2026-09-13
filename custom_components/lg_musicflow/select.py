"""Select platform for LG MusicFlow (Legacy)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    EQUALIZER_MAP,
    EQUALIZER_REVERSE_MAP,
    FUNCTION_MAP,
    FUNCTION_REVERSE_MAP,
)
from .coordinator import LGMusicFlowCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the LG Music Flow select entities."""
    coordinator: LGMusicFlowCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        LGMusicFlowSourceSelect(coordinator, entry),
        LGMusicFlowSoundModeSelect(coordinator, entry),
    ])


class LGMusicFlowBaseSelect(CoordinatorEntity[LGMusicFlowCoordinator], SelectEntity):
    """Base select entity for LG Music Flow."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LGMusicFlowCoordinator, entry: ConfigEntry) -> None:
        """Initialize the select entity."""
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


class LGMusicFlowSourceSelect(LGMusicFlowBaseSelect):
    """Select entity for input source."""

    _attr_name = "Source"
    _attr_icon = "mdi:audio-input-rca"

    def __init__(self, coordinator: LGMusicFlowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._mac}_source"

        info = coordinator.product_info.get("info", {})
        raw_func_list = info.get("functionlist", [])
        self._options = [
            FUNCTION_MAP[code] for code in raw_func_list if code in FUNCTION_MAP
        ]
        if not self._options:
            self._options = list(FUNCTION_MAP.values())

    @property
    def options(self) -> list[str]:
        """Return the available input sources."""
        return self._options

    @property
    def current_option(self) -> str | None:
        """Return the current input source."""
        fn_code = self.coordinator.data.get("func", {}).get("type")
        return FUNCTION_MAP.get(fn_code)

    async def async_select_option(self, option: str) -> None:
        """Change the input source."""
        fn_code = FUNCTION_REVERSE_MAP.get(option)
        if fn_code is not None:
            await self.coordinator.client.async_set_function(fn_code)
            await self.coordinator.async_request_refresh()


class LGMusicFlowSoundModeSelect(LGMusicFlowBaseSelect):
    """Select entity for sound mode (equalizer preset)."""

    _attr_name = "Sound Mode"
    _attr_icon = "mdi:equalizer"

    def __init__(self, coordinator: LGMusicFlowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._mac}_sound_mode"

        info = coordinator.product_info.get("info", {})
        raw_eq_list = info.get("eqlist", [])
        self._options = [
            EQUALIZER_MAP[code] for code in raw_eq_list if code in EQUALIZER_MAP
        ]
        if not self._options:
            self._options = ["Standard", "Cinema", "Music", "Bass Blast", "Dolby Atmos", "Adaptive Sound Control (ASC)"]

    @property
    def options(self) -> list[str]:
        """Return the available sound modes."""
        return self._options

    @property
    def current_option(self) -> str | None:
        """Return the current sound mode."""
        eq_code = self.coordinator.data.get("eq", {}).get("currenteq")
        return EQUALIZER_MAP.get(eq_code)

    async def async_select_option(self, option: str) -> None:
        """Change the sound mode."""
        eq_code = EQUALIZER_REVERSE_MAP.get(option)
        if eq_code is not None:
            await self.coordinator.client.async_set_sound_mode(eq_code)
            await self.coordinator.async_request_refresh()
