"""First attempt to implement PowerView individual shade control."""

import asyncio
import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.helpers import discovery
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

REQUIREMENTS = ["aiopvapi==1.6.14"]

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(DOMAIN, default={}): vol.Schema(
            {vol.Required(CONF_IP_ADDRESS): cv.string}
        )
    },
    extra=vol.ALLOW_EXTRA,
)

# todo: add scenes as components.

POWERVIEW_COMPONENTS = ["cover"]


async def get_shades(shades):
    shades = await shades.get_instances()
    return shades


async def async_setup(hass, config):
    """Set up a PowerView hub."""

    from aiopvapi.shades import Shades
    from aiopvapi.helpers.aiorequest import AioRequest, PvApiError

    conf = config.get(DOMAIN)

    ip = conf[CONF_IP_ADDRESS]
    websession = async_get_clientsession(hass)

    hub_request = AioRequest(ip, hass.loop, websession)

    shades_entry_point = Shades(hub_request)

    async def scan_for_shades(event_data=None):
        _tries = 3
        while _tries > 0:
            try:
                _LOGGER.debug("getting shades.")
                shades = await get_shades(shades_entry_point)
                break
            except PvApiError as err:
                _LOGGER.error(err)
                await asyncio.sleep(5)
        else:
            _LOGGER.error("Failed to setup PowerView shades.")
            return False

        _LOGGER.debug("recieved shades. %s", shades)
        hass.data[DOMAIN] = {"shades": shades}

        for component in POWERVIEW_COMPONENTS:
            await discovery.async_load_platform(
                hass, component, DOMAIN, {}, config
            )
    await scan_for_shades()

    hass.services.async_register(DOMAIN, "scan", scan_for_shades)

    return True
