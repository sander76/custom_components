"""Support for HomematicIP via Accesspoint."""

import asyncio
import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from datetime import timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.event import async_track_time_interval
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

RECONNECT_RETRY_DELAY = 1  # minutes

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
        self.ws_reconnect_handle = None

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.ws_close())

    @property
    def hmip_id(self):
        return self._home.id

    @property
    def home(self):
        return self._home

    @asyncio.coroutine
    def connect(self):
        yield from self._home.init(self._accesspoint)
        yield from self._home.get_current_state()

    @asyncio.coroutine
    def ws_connect(self, now=None):
        self._ws_close_requested = False

        if self.ws_reconnect_handle is not None:
            _LOGGER.debug("Retrying websocket connection.")
        try:
            # connect to the websocket server.

            ws_loop_future = yield from self._home.enable_events()
            _LOGGER.info("HMIP events enabled.")
        except HmipConnectionError as err:
            _LOGGER.error(err)
            if self.ws_reconnect_handle is None:

                # Do a connection retry every x minutes. Executing this handle
                # will cancel the task.
                _LOGGER.info(
                    "reconnecting in %s minutes", RECONNECT_RETRY_DELAY)
                self.ws_reconnect_handle = async_track_time_interval(
                    self._hass, self.ws_connect, timedelta(
                        minutes=RECONNECT_RETRY_DELAY)
                )
            return
        except Exception as err:
            _LOGGER.error("undefined error: %s", err)
            return

        # Connection succeeded. Remove any remaining reconnect handlers
        if self.ws_reconnect_handle is not None:
            self.ws_reconnect_handle()  # removes the handle task.
            self.ws_reconnect_handle = None

        _LOGGER.info("HMIP websocket connected.")

        try:
            yield from ws_loop_future
        except HmipConnectionError as err:
            _LOGGER.error(str(err))

        _LOGGER.info("Websocket closed.")

        # If websocket close was not requested, attempt to reconnect.
        if not self._ws_close_requested:
            # todo: Add Update_state call.
            # This establishes a new websocket
            # connection waiting for state changes. But in the meantime
            # state might have changed which is not propagated through the
            # websocket connection. A Update_state call should be added to
            # the reconnect method.
            _LOGGER.info("Websocket connection closed unintentionally. "
                         "Trying to reconnect.")
            self._hass.loop.create_task(self.ws_connect())

    @asyncio.coroutine
    def ws_close(self):
        """Close the websocket connection"""
        _LOGGER.info("Closing HMIP connection")
        self._ws_close_requested = True
        if self.ws_reconnect_handle is not None:
            _LOGGER.debug("Removing reconnection handler")
            # remove the handler
            self.ws_reconnect_handle()
            self.ws_reconnect_handle = None
        _LOGGER.debug("Disabling events.")
        yield from self._home.disable_events()
        _LOGGER.info("Closed HMIP connection")


@asyncio.coroutine
def async_setup(hass, config):
    """Setup the hmip platform."""
    from homematicip.base.base_connection import HmipConnectionError

    _LOGGER.debug("Setting up hmip platform")

    homematicip_hubs = config.get(DOMAIN, [])
    hass.data[DOMAIN] = {}
    for _hub_config in homematicip_hubs:
        websession = async_get_clientsession(hass)
        _hmip = HmipConnector(_hub_config, hass.loop, websession, hass)
        try:
            yield from _hmip.connect()
        except HmipConnectionError as err:
            # todo: create a retry here too.
            _LOGGER.error('Failed to connect to the HomeMatic cloud server.')
            return False
        else:
            hass.data[DOMAIN][_hmip.hmip_id] = _hmip.home

            for component in COMPONTENTS:
                hass.async_add_job(async_load_platform(
                    hass, component, DOMAIN,
                    {ATTR_HMIP_HOME_ID: _hmip.hmip_id},
                    config))

        hass.loop.create_task(_hmip.ws_connect())
    return True


# todo: For inspiration:
# Checkout hass.components.configurator as used by aioautomatic/automatic

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

    # @property
    # def entity_id(self):
    #     return self._entity_id

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
