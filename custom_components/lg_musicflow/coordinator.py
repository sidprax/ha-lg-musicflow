"""DataUpdateCoordinator for LG Music Flow speakers."""
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import LGMusicFlowClient, LGMusicFlowError
from .const import DOMAIN, STATE_PLAYING

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL_NORMAL = timedelta(seconds=6)
SCAN_INTERVAL_FAST = timedelta(seconds=3)


class LGMusicFlowCoordinator(DataUpdateCoordinator):
    """Coordinator to manage polling of speaker state."""

    def __init__(self, hass: HomeAssistant, client: LGMusicFlowClient, product_info: dict) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.product_info = product_info
        super().__init__(
            hass,
            _LOGGER,
            name=f"LG Music Flow ({client.host})",
            update_interval=SCAN_INTERVAL_NORMAL,
        )

    async def _async_update_data(self) -> dict:
        """Fetch the latest status from the speaker."""
        try:
            data = await self.client.async_get_status()
            
            # If actively playing, increase polling frequency so progress/state is snappy
            play_state = data.get("play", {}).get("playing", -1)
            if play_state == STATE_PLAYING:
                self.update_interval = SCAN_INTERVAL_FAST
            else:
                self.update_interval = SCAN_INTERVAL_NORMAL

            return data
        except LGMusicFlowError as err:
            raise UpdateFailed(f"Error fetching data from speaker: {err}") from err
