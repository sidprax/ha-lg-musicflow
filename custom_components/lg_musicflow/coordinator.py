"""DataUpdateCoordinator for LG Music Flow speakers."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import LGMusicFlowClient, LGMusicFlowError
from .const import (
    CONF_PAUSE_STANDBY_POLLING,
    CONF_SCAN_INTERVAL,
    DEFAULT_PAUSE_STANDBY_POLLING,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STANDBY_SCAN_INTERVAL,
    STATE_PLAYING,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL_NORMAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
SCAN_INTERVAL_FAST = timedelta(seconds=3)
SCAN_INTERVAL_STANDBY = timedelta(seconds=DEFAULT_STANDBY_SCAN_INTERVAL)


class LGMusicFlowCoordinator(DataUpdateCoordinator):
    """Coordinator to manage polling of speaker state."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: LGMusicFlowClient,
        product_info: dict[str, Any],
        entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.product_info = product_info
        self.entry = entry

        scan_sec = (
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            if entry
            else DEFAULT_SCAN_INTERVAL
        )
        self.normal_interval = timedelta(seconds=scan_sec)
        self.fast_interval = timedelta(seconds=min(3, scan_sec))
        self.standby_interval = timedelta(
            seconds=max(DEFAULT_STANDBY_SCAN_INTERVAL, scan_sec * 2)
        )
        self.pause_standby = (
            entry.options.get(
                CONF_PAUSE_STANDBY_POLLING, DEFAULT_PAUSE_STANDBY_POLLING
            )
            if entry
            else DEFAULT_PAUSE_STANDBY_POLLING
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"LG Music Flow ({client.host})",
            update_interval=self.normal_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest status from the speaker."""
        try:
            data = await self.client.async_get_status()

            func = data.get("func", {})
            func_type = func.get("type", 0)
            play_state = data.get("play", {}).get("playing", -1)

            if play_state == STATE_PLAYING:
                self.update_interval = self.fast_interval
            elif func_type == 0:
                if self.pause_standby:
                    self.update_interval = None
                else:
                    self.update_interval = self.standby_interval
            else:
                self.update_interval = self.normal_interval

            return data
        except LGMusicFlowError as err:
            if self.pause_standby:
                self.update_interval = None
            raise UpdateFailed(f"Error fetching data from speaker: {err}") from err
