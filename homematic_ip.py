"""
Support for HomematicIP via Accesspoint.
"""

import asyncio
import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback, CoreState
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'homematic_ip'
DOMAIN_ACCESSPOINT_CHANGED = 'homematicip_accesspoint_changed'
DOMAIN_DEVICE_CHANGED = 'homematicip_device_changed'
DOMAIN_GROUP_CHANGED = 'homematicip_group_changed'

CONF_NAME = 'name'
CONF_ACCESSPOINT = 'accesspoint'
CONF_AUTHTOKEN = 'authtoken'

ATTR_HMIP_ID = 'device_id'
ATTR_HMIP_HOME_ID = 'home_id'
ATTR_HMIP_HOME = 'home'
ATTR_HMIP_LAST_UPDATE = 'last_update'

# ATTR_HMIP_FIRMWARE = 'status_firmware'
# ATTR_HMIP_ACTUAL_FIRMWARE = 'actual_firmware'
# ATTR_HMIP_AVAILABLE_FIRMWARE = 'available_firmware'
ATTR_HMIP_LOW_BATTERY = 'low_battery'
ATTR_HMIP_UNREACHABLE = 'not_reachable'
# ATTR_HMIP_SABOTAGE = 'sabotage'
# ATTR_HMIP_UPTODATE = 'up_to_date'
# ATTR_HMIP_WINDOW = 'window'
# ATTR_HMIP_ON = 'on'
# ATTR_HMID_CURRENT_POWER_CONSUMPTION = 'currentPowerConsumption'
# ATTR_HMID_ENERGY_COUNTER = 'energyCounter'

COMPONTENTS = [
    'sensor',
    # 'climate',
    'switch',
    # 'light',
    'binary_sensor',
    # 'alarm_control_panel'
]

SIGNAL_UPDATE = 'homematicip.update'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.All(cv.ensure_list, [vol.Schema({
        vol.Optional(CONF_NAME): cv.string,
        vol.Required(CONF_ACCESSPOINT): cv.string,
        vol.Required(CONF_AUTHTOKEN): cv.string
    })])
}, extra=vol.ALLOW_EXTRA)


@asyncio.coroutine
def setup_home(config, loop, websession):
    from homematicip.base.base_connection import HmipConnectionError
    """Create a hmip home instance.

    During creation several requests are made to the hmip server.
    If a problem occurs a 'ConnectionError' is thrown.
    """
    _LOGGER.info("Setting up hmip home")
    from homematicip.async.home import AsyncHome

    _accesspoint = config.get(CONF_ACCESSPOINT)
    _authtoken = config.get(CONF_AUTHTOKEN)

    home = AsyncHome(loop, websession)
    home.set_auth_token(_authtoken)

    yield from home.init(_accesspoint)

    yield from home.get_current_state()

    def connect_to_websocket():
        home.enable_events()
        home.on_connection_lost(reconnect)

    # todo: add a callback when the task finishes (crashes) this will
    # catch any exception thrown by the websocket connection.
    # https://medium.com/@yeraydiazdiaz/asyncio-coroutine-patterns-errors-and-cancellation-3bb422e961ff
    # home.enable_events()

    def reconnect(future_: asyncio.Future):
        """Schedule a reconnect when websocket connection has gone"""
        try:
            _result = future_.result()
        except HmipConnectionError as err:
            _LOGGER.warning(err)
            asyncio.sleep(2)
            connect_to_websocket()
        except Exception as err:
            _LOGGER.exception(err)
            asyncio.sleep(2)
            connect_to_websocket()

    connect_to_websocket()

    return home


async def stop_hmip(hmip):
    """Stop the hmip websocket connection."""
    hmip.disable_events()


@asyncio.coroutine
def async_setup(hass, config):
    """Setup the hmip platform."""
    from homematicip.base.base_connection import HmipConnectionError

    _LOGGER.debug("Setting up hmip platform")
    @callback
    def stop_callback(_event):
        """Stop listening for incoming websocket data."""
        for _hmip in hass.data[DOMAIN].values():
            hass.async_add_job(stop_hmip(_hmip))

    hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP,
        stop_callback
    )

    homematicip_hubs = config.get(DOMAIN, [])
    for _hub_config in homematicip_hubs:
        hass.data[DOMAIN] = {}
        try:
            websession = async_get_clientsession(hass)
            _hmip = yield from setup_home(_hub_config, hass.loop, websession)
        except HmipConnectionError as err:
            _LOGGER.error('Failed to connect to the HomeMatic cloud server.')
            return False
        else:
            hass.data[DOMAIN][_hmip.id] = _hmip

            for component in COMPONTENTS:
                hass.async_add_job(async_load_platform(
                    hass, component, DOMAIN, {ATTR_HMIP_HOME_ID: _hmip.id},
                    config))

    return True


class HmipGenericDevice(Entity):
    """Representation of an HomeMaticIP device."""

    def __init__(self, hass, home, device):
        """Initialize the generic device."""
        self.hass = hass
        #self._home = home
        self._device = device

        self._device_state_attributes = {
            ATTR_HMIP_ID: self._device.id,
            ATTR_HMIP_HOME_ID: home.id
        }
        self._device.on_update(self.push_update)

    def push_update(self, js):
        """Update the hmip device."""
        self.async_schedule_update_ha_state()

    @property
    def name(self):
        """Return the name of the generic device."""
        return '{}'.format(self._device.label)

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def available(self):
        """Check for device availability."""
        return not self._device.unreach

    def _get_attribute(self, attribute, attribute_key) -> dict:
        _attr = {}
        try:
            _val = getattr(self._device, attribute)
            if _val is not None:
                _attr = {attribute_key: _val}
        except AttributeError:
            _attr = {}
        return _attr

    @property
    def device_state_attributes(self):
        """Return device state attributes."""
        self._device_state_attributes[
            ATTR_HMIP_LOW_BATTERY] = self._device.lowBat
        self._device_state_attributes[
            ATTR_HMIP_LAST_UPDATE] = self._device.lastStatusUpdate
        self._device_state_attributes[
            ATTR_HMIP_UNREACHABLE] = self._device.unreach
        return self._device_state_attributes
