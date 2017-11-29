"""
Support for HomematicIP via Accesspoint.

binary_sensor: Switch
"""
import asyncio
import logging

from homeassistant.components.switch import SwitchDevice
from homematicip.async.device import AsyncPlugableSwitchMeasuring, \
    AsyncPlugableSwitch

# from homeassistant.components.homematic_ip import HmipGenericDevice
# from custom_components.homematic_ip import HmipGenericDevice
from ..homematic_ip import HmipGenericDevice

_LOGGER = logging.getLogger(__name__)


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up the device."""
    _LOGGER.info("Setting up HomeMaticIP switch")
    _devices = []
    home = discovery_info['home']
    for _device in home.devices:
        if isinstance(_device, AsyncPlugableSwitchMeasuring):
            _devices.append(
                HmipPlugableSwitchMeasuring(hass, home, _device)
            )
        elif isinstance(_device, AsyncPlugableSwitch):
            _devices.append(
                HmipPlugableSwitch(hass, home, _device))

    if _devices:
        async_add_devices(_devices)
    return True


class HmipPlugableSwitch(HmipGenericDevice, SwitchDevice):
    """HomematicIP Plugable switch."""

    async def async_turn_off(self, **kwargs):
        """Switch off."""
        await self._device.turn_off()

    async def async_turn_on(self, **kwargs):
        """Switch on."""
        await self._device.turn_on()

    @property
    def is_on(self) -> bool:
        """Return true if device is on."""
        return self._device.on


class HmipPlugableSwitchMeasuring(HmipPlugableSwitch):
    """HomematicIP Plugable switch with energy consumption metering."""

    @property
    def current_power_w(self):
        """Return the current power usage in W."""
        return self._device.currentPowerConsumption

    @property
    def today_energy_kwh(self):
        """Return the power usage in kWh."""
        return self._device.energyCounter
