"""
Support for HomematicIP via Accesspoint.
sensor: Multiple sensors.
"""
import asyncio
import logging

from homeassistant.const import TEMP_CELSIUS
from homematicip.async.device import \
    AsyncTemperatureHumiditySensorWithoutDisplay, \
    AsyncTemperatureHumiditySensorDisplay

from ..homematic_ip import DOMAIN, ATTR_HMIP_HOME_ID
from ..homematic_ip import HmipGenericDevice

# from homeassistant.components.homematic_ip import HmipGenericDevice
# from custom_components.homematic_ip import HmipGenericDevice

_LOGGER = logging.getLogger(__name__)

TEMPERATURE_SENSORS = (AsyncTemperatureHumiditySensorWithoutDisplay,
                       AsyncTemperatureHumiditySensorDisplay)

HUMIDITY_SENSORS = (AsyncTemperatureHumiditySensorDisplay,
                    AsyncTemperatureHumiditySensorWithoutDisplay)


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    _LOGGER.info("Setting up HomeMaticIP sensor")

    _devices = []
    # home = discovery_info['home']
    home = hass.data[DOMAIN][discovery_info[ATTR_HMIP_HOME_ID]]
    for device in home.devices:

        if isinstance(device, TEMPERATURE_SENSORS):
            _devices.append(
                HmipTemperatureSensor(hass, home, device))
        if isinstance(device, HUMIDITY_SENSORS):
            _devices.append(
                HmipHumiditySensor(hass, home, device))
    if _devices:
        async_add_devices(_devices)
    return True


class HmipTemperatureSensor(HmipGenericDevice):
    """HomematicIP temperature sensor."""

    def __init__(self, hass, home, device, unit_of_measurement=TEMP_CELSIUS):
        """Initialize the device."""
        super().__init__(hass, home, device)
        self._unit_of_measurement = unit_of_measurement

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement this sensor expresses itself in."""
        return self._unit_of_measurement

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._device.actualTemperature


class HmipHumiditySensor(HmipGenericDevice):
    """HomematicIP humidity sensor."""

    def __init__(self, hass, home, device, unit_of_measurement='%'):
        """Initialize the device."""
        super().__init__(hass, home, device)
        self._unit_of_measurement = unit_of_measurement

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement this sensor expresses itself in."""
        return self._unit_of_measurement

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._device.humidity
