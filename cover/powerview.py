import logging

from aiopvapi.helpers.aiorequest import PvApiError
from aiopvapi.resources.shade import BaseShade, MAX_POSITION

from homeassistant.components.cover import CoverDevice
from custom_components.powerview.const import DOMAIN

LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass, config, async_add_entities, discovery_info=None
):

    devices = []
    for device in hass.data[DOMAIN]["shades"]:
        devices.append(PowerViewDevice(device))

    async_add_entities(devices)


def _two_byte_to_percentage(position: int) -> int:

    return int(position / MAX_POSITION * 100)


class PowerViewDevice(CoverDevice):
    """PowerView cover class."""

    def __init__(self, shade_instance: BaseShade):
        self.shade_instance = shade_instance

        self._current_tilt_position = None
        if shade_instance.can_tilt:
            self._current_tilt_position = 50

        self._current_cover_position = None
        if shade_instance.can_move:
            self._current_move_position = 50

        self._closed = True

    async def async_update(self):
        # PowerView does have an update position method.
        # However, it makes the hub unresponsive for about 4 seconds.
        # For smooth user operation this is too long. Therefore not
        # implemented.
        pass

    @property
    def name(self):
        """Return name of the shade."""
        return self.shade_instance.name

    async def async_open_cover(self, **kwargs):
        LOGGER.debug("open cover")
        await self.api_call(self.shade_instance.open)

    async def async_close_cover(self, **kwargs):
        LOGGER.debug("close cover")
        await self.api_call(self.shade_instance.close)

    async def async_stop_cover(self, **kwargs):
        LOGGER.debug("stopping cover")
        await self.api_call(self.shade_instance.stop)

    async def async_stop_cover_tilt(self, **kwargs):
        LOGGER.debug("stop tilt")
        await self.api_call(self.shade_instance.stop)

    async def async_close_cover_tilt(self, **kwargs):
        LOGGER.debug("close cover")
        await self.api_call(self.shade_instance.tilt_close)

    async def async_open_cover_tilt(self, **kwargs):
        LOGGER.debug("open tilt")
        await self.api_call(self.shade_instance.tilt_open)

    async def api_call(self, call):
        try:
            await call()
        except PvApiError as err:
            LOGGER.error(err)

    @property
    def current_cover_position(self):
        return self._current_cover_position

    @property
    def current_cover_tilt_position(self):
        return self._current_tilt_position

    @property
    def unique_id(self):
        """Return a unique ID."""
        return "{}_{}".format(self.__class__.__name__, self.shade_instance.id)

    @property
    def is_closed(self):
        return None
