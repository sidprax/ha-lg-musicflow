"""Media Player platform for LG MusicFlow (Legacy)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    BrowseError,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)
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
    STATE_BUFFERING,
    STATE_PAUSED,
    STATE_PLAYING,
)
from .coordinator import LGMusicFlowCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the LG Music Flow media player entity."""
    coordinator: LGMusicFlowCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LGMusicFlowMediaPlayer(coordinator, entry)])


class LGMusicFlowMediaPlayer(CoordinatorEntity[LGMusicFlowCoordinator], MediaPlayerEntity):
    """Representation of an LG Music Flow soundbar/speaker."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER

    def __init__(self, coordinator: LGMusicFlowCoordinator, entry: ConfigEntry) -> None:
        """Initialize the media player."""
        super().__init__(coordinator)
        self._entry = entry
        
        info = coordinator.product_info.get("info", {})
        self._mac = info.get("wirelessmac") or info.get("btmac") or entry.data["host"]
        self._model = coordinator.product_info.get("modelname", "Music Flow")
        self._sw_version = info.get("bever")
        self._attr_unique_id = f"{self._mac}_media_player"

        # Build dynamic source list based on what this speaker model reports
        raw_func_list = info.get("functionlist", [])
        self._sources = [
            FUNCTION_MAP[code] for code in raw_func_list if code in FUNCTION_MAP
        ]
        if not self._sources:
            self._sources = list(FUNCTION_MAP.values())

        # Build dynamic sound mode list based on what this speaker model reports
        raw_eq_list = info.get("eqlist", [])
        self._sound_modes = [
            EQUALIZER_MAP[code] for code in raw_eq_list if code in EQUALIZER_MAP
        ]
        if not self._sound_modes:
            self._sound_modes = ["Standard", "Cinema", "Music", "Bass Blast", "Dolby Atmos", "Adaptive Sound Control (ASC)"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            name=self._entry.data.get(CONF_NAME, f"LG {self._model}"),
            manufacturer="LG Electronics",
            model=self._model,
            sw_version=self._sw_version,
        )

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        return (
            MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.SELECT_SOUND_MODE
            | MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
            | MediaPlayerEntityFeature.BROWSE_MEDIA
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.TURN_ON
        )

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the player."""
        play_data = self.coordinator.data.get("play", {})
        play_code = play_data.get("playing", -1)

        if play_code == STATE_PLAYING:
            return MediaPlayerState.PLAYING
        if play_code == STATE_PAUSED:
            return MediaPlayerState.PAUSED
        if play_code == STATE_BUFFERING:
            return MediaPlayerState.BUFFERING

        func_type = self.coordinator.data.get("func", {}) .get("type", 0)
        # If active on a physical input (Optical, HDMI, Aux, BT), consider ON
        if func_type in (1, 3, 4, 6, 7, 15):
            return MediaPlayerState.ON

        return MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        vol = self.coordinator.data.get("settings", {}).get("vol")
        if vol is None:
            vol = self.coordinator.product_info.get("info", {}).get("vol")
        if vol is not None:
            return max(0.0, min(1.0, float(vol) / 100.0))
        return None

    @property
    def is_volume_muted(self) -> bool | None:
        """Boolean if volume is currently muted."""
        return self.coordinator.data.get("func", {}).get("mute")

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        return self._sources

    @property
    def source(self) -> str | None:
        """Current input source."""
        fn_code = self.coordinator.data.get("func", {}).get("type")
        if fn_code in (4, 7, 15) and "Optical / HDMI ARC" in self._sources:
            return "Optical / HDMI ARC"
        return FUNCTION_MAP.get(fn_code)

    @property
    def sound_mode_list(self) -> list[str]:
        """List of available sound modes (equalizer presets)."""
        return self._sound_modes

    @property
    def sound_mode(self) -> str | None:
        """Current sound mode (equalizer preset)."""
        eq_code = self.coordinator.data.get("eq", {}).get("currenteq")
        return EQUALIZER_MAP.get(eq_code)

    @property
    def media_title(self) -> str | None:
        """Title of current playing media."""
        return self.coordinator.data.get("play", {}).get("title") or None

    @property
    def media_artist(self) -> str | None:
        """Artist of current playing media."""
        return self.coordinator.data.get("play", {}).get("artist") or None

    @property
    def media_duration(self) -> int | None:
        """Duration of current playing media in seconds."""
        dur = self.coordinator.data.get("play", {}).get("duration")
        return int(dur) if dur else None

    @property
    def media_position(self) -> int | None:
        """Position of current playing media in seconds."""
        pos = self.coordinator.data.get("play", {}).get("position")
        return int(pos) if pos is not None else None

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        target_vol = int(round(volume * 100))
        await self.coordinator.client.async_set_volume(target_vol)
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute (true) or unmute (false) media player."""
        await self.coordinator.client.async_set_mute(mute)
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        fn_code = FUNCTION_REVERSE_MAP.get(source)
        if fn_code is not None:
            await self.coordinator.client.async_set_function(fn_code)
            await self.coordinator.async_request_refresh()

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Select sound mode (equalizer preset)."""
        eq_code = EQUALIZER_REVERSE_MAP.get(sound_mode)
        if eq_code is not None:
            await self.coordinator.client.async_set_sound_mode(eq_code)
            await self.coordinator.async_request_refresh()

    async def async_media_play(self) -> None:
        """Send play command."""
        await self.coordinator.client.async_media_play()
        await self.coordinator.async_request_refresh()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self.coordinator.client.async_media_pause()
        await self.coordinator.async_request_refresh()

    async def async_media_stop(self) -> None:
        """Send stop command."""
        if self.state in (MediaPlayerState.PLAYING, MediaPlayerState.PAUSED, MediaPlayerState.BUFFERING):
            try:
                await self.coordinator.client.async_media_stop()
            except Exception:
                pass
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off media player (stop playback and return to Wi-Fi standby)."""
        if self.state in (MediaPlayerState.PLAYING, MediaPlayerState.PAUSED, MediaPlayerState.BUFFERING):
            try:
                await self.coordinator.client.async_media_stop()
            except Exception:
                pass
        await self.coordinator.client.async_set_function(0)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on media player (set to Wi-Fi mode)."""
        await self.coordinator.client.async_set_function(0)
        await self.coordinator.async_request_refresh()

    async def async_play_media(
        self,
        media_type: MediaType | str,
        media_id: str,
        **kwargs: Any,
    ) -> None:
        """Play a piece of media."""
        # Handle media_source (local files, TTS, radio)
        if media_source.is_media_source_id(media_id):
            sourced_media = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            media_id = sourced_media.url

        # Format URL with HA base if relative
        media_id = async_process_play_media_url(self.hass, media_id)

        title = kwargs.get("extra", {}).get("title") or "Home Assistant"
        artist = kwargs.get("extra", {}).get("artist") or "Media Player"

        _LOGGER.info("Streaming media to LG Music Flow (%s): %s", self.name, media_id)
        await self.coordinator.client.async_play_media(media_id, title=title, artist=artist)
        await self.coordinator.async_request_refresh()

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> Any:
        """Implement the websocket media browsing helper."""
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )
