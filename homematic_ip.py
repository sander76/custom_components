"""Support for HomematicIP via Accesspoint."""

import asyncio
import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
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

EVENT_HMIP_ACCESSPOINT_STATE_CHANGED = 'hmip_state_changed'

STATE_CONNECTING = 'connecting'
STATE_CONNECTED = 'connected'
STATE_DISCONNECTED = 'disconnected'


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
        self._home.on_update(self.update)
        self._previous_connection_state = True
        # hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.ws_close())

    def update(self, *args, **kwargs):
        """Update the home device.

        Triggered when the hmip HOME_CHANGED event has fired.
        There are several occasions when this event might happen.
        We are only interested in this event to check whether the home is
        still connected."""
        if not self._home.connected:
            _LOGGER.error(
                "HMIP access point has lost connection with the cloud")
            self._previous_connection_state = False
            self.set_all_to_unavailable()
        else:
            if not self._previous_connection_state:
                # only update the state when connection state has gone from
                # false to true
                job = self._hass.async_add_job(self.get_state())
                job.add_done_callback(self.get_state_finished)

    async def get_state(self):
        """Update hmip state and tell hass."""
        await self._home.get_current_state()
        self.update_all()

    def get_state_finished(self, future):
        try:
            future.result()
        except HmipConnectionError:
            # Somehow connection could not recover. Will disconnect and
            # so reconnect loop is taking over.
            _LOGGER.error(
                "updating state after himp access point reconnect failed.")
            self._hass.async_add_job(self._home.disable_events())

    @property
    def hmip_id(self):
        return self._home.id

    @property
    def home(self):
        return self._home

    @property
    def devices(self):
        return self._home.devices

    async def init_connection(self):
        """Initialize HMIP cloud connection"""
        await self._home.init(self._accesspoint)
        await self._home.get_current_state()

    def set_all_to_unavailable(self):
        """Set all devices to unavailable"""

        for device in self._home.devices:
            device.unreach = True
        self.update_all()

    def set_all_to_available(self):
        """Sets all devices to available"""

        for device in self._home.devices:
            device.unreach = False
        self.update_all()

    def update_all(self):
        """Signal all devices to update their state."""

        for device in self._home.devices:
            device.fire_update_event()

    async def _handle_connection(self):
        await self._home.get_current_state()
        self.update_all()

        hmip_events = await self._home.enable_events()

        await hmip_events

    async def connect(self):
        self.tries = 0
        while True:
            try:
                await self._handle_connection()
            except HmipConnectionError:
                _LOGGER.error("HMIP cloud connection error")

                # todo: add persistent notification here.

                self.set_all_to_unavailable()
            except Exception:  # pylint: disable=broad-except
                # Safety net. This should never hit.
                # Still adding it here to make sure we can always reconnect
                _LOGGER.exception("Unexpected error")

                self.set_all_to_unavailable()

            if self._ws_close_requested:
                break

            self._ws_close_requested = False

            self.tries += 1

            try:
                self.retry_task = self._hass.async_add_job(asyncio.sleep(
                    2 ** min(9, self.tries), loop=self._hass.loop))
                await self.retry_task
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
        self._device = device

        self._device_state_attributes = {
            ATTR_HMIP_LABEL: self._device.label,
            ATTR_HMIP_HOME_ID: home.id
        }
        self._device.on_update(self.push_update)
        self.entity_id = async_generate_entity_id(
            entity_id_format, self._unique_id(), hass=hass)
        # self.hass.async_listen(EVENT_HMIP_ACCESSPOINT_STATE_CHANGED,
        #                        self.change_state)

    def change_state(self, event):
        _LOGGER.debug("state changed {}".format(event))
        if event.data.get(
                ATTR_HMIP_HOME_ID) == self._device_state_attributes.get(
            ATTR_HMIP_HOME_ID):
            # todo: interpret the state change
            pass

    def push_update(self, *args, **kwargs):
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
