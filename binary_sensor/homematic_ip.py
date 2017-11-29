"""
Support for HomematicIP via Accesspoint.
binary_sensor: ShutterContact
"""
import asyncio
import logging

from homeassistant.components.binary_sensor import BinarySensorDevice, \
    DEVICE_CLASSES
from homematicip.async.device import AsyncShutterContact

# from custom_components.homematic_ip import HmipGenericDevice
from ..homematic_ip import DOMAIN, ATTR_HMIP_HOME_ID
from ..homematic_ip import HmipGenericDevice

# from homeassistant.components.homematic_ip import HmipGenericDevice

_LOGGER = logging.getLogger(__name__)

# ATTR_EVENT_DELAY = 'event_delay'
# ATTR_STATE_LOW_BAT = 'low_battery'
# ATTR_STATE_NOT_REACHABLE = 'not_reachable'
# ATTR_EVENT_MOTION = 'event_motion'
# ATTR_STATE_ILUMINATION = 'ilumination'


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    _LOGGER.info("Setting up HomeMaticIP binary sensor")
    OPEN = 'opening'
    if OPEN not in DEVICE_CLASSES:
        return False
    _devices = []
    home = hass.data[DOMAIN][discovery_info[ATTR_HMIP_HOME_ID]]
    #home = discovery_info['home']
    for device in home.devices:
        if isinstance(device, AsyncShutterContact):
            _devices.append(
                HmipShutterContact(hass, home, device, OPEN))
    if _devices:
        async_add_devices(_devices)
    return True


class HmipShutterContact(HmipGenericDevice,
                         BinarySensorDevice):
    """HomematicIP ShutterContact."""

    def __init__(self, hass, home, device, device_class):
        """Initialize the device."""
        super().__init__(hass, home, device)
        self._device_class = device_class

    @property
    def is_on(self):
        """Return true if device is open."""
        if self._device.windowState == "OPEN":
            return True
        else:
            return False

    @property
    def device_class(self):
        """Return the class of this sensor, from DEVICE_CLASSES."""
        return self._device_class
