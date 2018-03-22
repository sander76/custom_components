"""Support for HomematicIP via Accesspoint."""

import asyncio
import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homematicip.base.base_connection import HmipConnectionError

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'homematic_ip'
DOMAIN_ACCESSPOINT_CHANGED = 'homematicip_accesspoint_changed'
DOMAIN_DEVICE_CHANGED = 'homematicip_device_changed'
DOMAIN_GROUP_CHANGED = 'homematicip_group_changed'

CONF_HOME_NAME = 'name'
CONF_ACCESSPOINT = 'accesspoint'
CONF_AUTHTOKEN = 'authtoken'

ATTR_HMIP_ID = 'device_id'
ATTR_HMIP_HOME_ID = 'home_id'
# ATTR_HMIP_HOME = 'home'
ATTR_HMIP_LABEL = 'label'
ATTR_HMIP_LAST_UPDATE = 'last_update'

ATTR_HMIP_LOW_BATTERY = 'low_battery'
ATTR_HMIP_UNREACHABLE = 'not_reachable'

RECONNECT_RETRY_DELAY = 5  # minutes

COMPONTENTS = [
    'sensor',
    # 'climate',
    'switch',
    # 'light',
    'binary_sensor',
    # 'alarm_control_panel'
]

SIGNAL_UPDATE = 'homematicip.update'

# todo: if provided use CONF_HOME_NAME as the access point id.

# todo: Add periodic update_state call to check whether access point is still there

# todo: during connection retry status should be set to unavailable.

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.All(cv.ensure_list, [vol.Schema({
        vol.Optional(CONF_HOME_NAME): cv.string,
        vol.Required(CONF_ACCESSPOINT): cv.string,
        vol.Required(CONF_AUTHTOKEN): cv.string
    })])
}, extra=vol.ALLOW_EXTRA)


class HmipConnector:
    """
    A HmipHome connection.

    Manages hmip http and websocket connection.

    Connection logic massively inspired by HASS automatic (aioautomatic)
    component.
    """

    def __init__(self, config, loop, websession, hass):
        from homematicip.async.home import AsyncHome
        self._hass = hass
        self._accesspoint = config.get(CONF_ACCESSPOINT)
        self._authtoken = config.get(CONF_AUTHTOKEN)
        self._home = AsyncHome(loop, websession)
        self._home.set_auth_token(self._authtoken)
        self._ws_close_requested = False
        self.retry_task = None
        self.tries = 0
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.ws_close())

    @property
    def hmip_id(self):
        return self._home.id

    @property
    def home(self):
        return self._home

    async def init_connection(self):
        await self._home.init(self._accesspoint)
        await self._home.get_current_state()

    async def _handle_connection(self):
        await self._home.get_current_state()

        hmip_events = await self._home.enable_events()
        try:
            await hmip_events
        except HmipConnectionError:
            # todo: add persistent notification here.
            return

    async def connect(self):
        self.tries = 0
        while True:
            try:
                await self._handle_connection()
            except Exception:  # pylint: disable=broad-except
                # Safety net. This should never hit.
                # Still adding it here to make sure we can always reconnect
                _LOGGER.exception("Unexpected error")
            if self._ws_close_requested:
                break

            self._ws_close_requested = False

            self.tries += 1

            try:
                self.retry_task = self._hass.async_add_job(asyncio.sleep(
                    2 ** min(9, self.tries), loop=self._hass.loop))
            except asyncio.CancelledError:
                break

    async def ws_close(self):
        """Close the websocket connection"""
        _LOGGER.info("Closing HMIP connection")
        self._ws_close_requested = True

        if self.retry_task is not None:
            self.retry_task.cancel()
        _LOGGER.debug("Disabling events.")
        await self._home.disable_events()
        _LOGGER.info("Closed HMIP connection")


async def async_setup(hass, config):
    """Setup the hmip platform."""
    from homematicip.base.base_connection import HmipConnectionError

    _LOGGER.debug("Setting up hmip platform")

    homematicip_hubs = config.get(DOMAIN, [])
    hass.data[DOMAIN] = {}
    for _hub_config in homematicip_hubs:
        websession = async_get_clientsession(hass)
        _hmip = HmipConnector(_hub_config, hass.loop, websession, hass)
        try:
            await _hmip.init_connection()
        except HmipConnectionError:
            # todo: create a retry here too.
            _LOGGER.error('Failed to connect to the HomeMatic cloud server.')
            return False
        except Exception as err:
            _LOGGER.error(err)
            return False
        hass.data[DOMAIN][_hmip.hmip_id] = _hmip.home

        for component in COMPONTENTS:
            hass.async_add_job(async_load_platform(
                hass, component, DOMAIN,
                {ATTR_HMIP_HOME_ID: _hmip.hmip_id},
                config))

        hass.loop.create_task(_hmip.connect())
    return True


class HmipGenericDevice(Entity):
    """Representation of an HomeMaticIP device."""

    def __init__(self, hass, home, device, entity_id_format):
        """Initialize the generic device."""
        self.hass = hass
        # self._home = home
        self._device = device

        self._device_state_attributes = {
            ATTR_HMIP_LABEL: self._device.label,
            ATTR_HMIP_HOME_ID: home.id
        }
        self._device.on_update(self.push_update)
        self.entity_id = async_generate_entity_id(
            entity_id_format, self._unique_id(), hass=hass)

    def push_update(self, js, **kwargs):
        """Update the hmip device."""
        self.async_schedule_update_ha_state()

    def _unique_id(self):
        return '{}_{}'.format(self.__class__.__name__, self._device.id)

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
            ATTR_HMIP_LAST_UPDATE] = self._device.lastStatusUpdate.strftime(
            '%Y-%m-%d %H:%M:%S')
        self._device_state_attributes[
            ATTR_HMIP_UNREACHABLE] = self._device.unreach
        return self._device_state_attributes
