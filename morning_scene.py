"""Activate a scene based on a variety of conditions."""
import logging
from functools import partial
from typing import Optional
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
import voluptuous as vol
from homeassistant.core import callback

# from homeassistant.helpers.condition import time
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_point_in_time,
)
from homeassistant.helpers.sun import get_astral_event_next
from datetime import datetime, time

from homeassistant.util.dt import UTC, DEFAULT_TIME_ZONE

LOGGER = logging.getLogger(__name__)


DOMAIN = "morning_scene"

CONF_BEFORE = "before"
CONF_AFTER = "after"
# CONF_SCENE_ID = "scene_id"

# CONFIG_SCHEMA = vol.Schema(
#     {
#         DOMAIN: vol.Schema(
#             {
#                 vol.Optional(CONF_BEFORE): cv.time,
#                 vol.Optional(CONF_AFTER): cv.time,
#             }
#         )
#     },
#     extra=vol.ALLOW_EXTRA,
# )


async def activate_scene(
    hass, entity_id, point_in_time: Optional[datetime] = None
):
    async def activate():
        LOGGER.debug("Activating scene.")
        hass.bus.async_fire(
            "scene.turn_on", event_data={"entity_id": entity_id}
        )

    if point_in_time is not None:
        async_track_point_in_time(hass, activate, point_in_time)

    else:
        await activate()


def set_time_at_date(local_now: datetime, time: time):
    local_time = datetime.combine(
        local_now.date(), time, tzinfo=local_now.tzinfo
    )
    return local_time


# {"after":"20:00","before":"21:00","entity_id":"abv"}


def get_dawn(local_now, hass):
    """Returns the next occurring dawn. Local time."""
    current_day_utc = dt_util.as_utc(local_now).date()
    start_of_day_utc = datetime.combine(
        current_day_utc, time(hour=0, minute=0), tzinfo=UTC
    )
    next_dawn = dt_util.as_local(
        get_astral_event_next(hass, "dawn", utc_point_in_time=start_of_day_utc)
    )
    return next_dawn


async def flow(
    hass, now: datetime, before: datetime, after: datetime, scene_id: str
):
    if after < now < before:
        LOGGER.info("Morning scenario")

        next_dawn = get_dawn(now, hass)

        LOGGER.debug("next dawn: %s", next_dawn)

        if now >= next_dawn:
            LOGGER.info("Dawn has passed. Activating scene.")
            # activate the up scene.
            await activate_scene(hass, scene_id)

        elif next_dawn > before:
            LOGGER.info("Scheduling scene activation at morning end.")
            await activate_scene(hass, scene_id, before)

        else:
            LOGGER.info("Scheduling scene activation at Dawn")
            # schedule the shade activation at dawn
            await activate_scene(hass, scene_id, next_dawn)
    else:
        LOGGER.debug("Current time outside morning time frame.")


async def async_setup(hass, config):
    """Setup the component."""

    # before = config[DOMAIN].get(CONF_BEFORE)
    # after = config[DOMAIN].get(CONF_AFTER)

    async def async_activate(call):
        LOGGER.debug("Service activated")

        entity_id = call.data.get("entity_id")

        if entity_id is None:
            LOGGER.error("Service called without required entity_id")
            return

        local_now = dt_util.now()

        try:
            _before = set_time_at_date(
                local_now, dt_util.parse_time(call.data[CONF_BEFORE])
            )
        except KeyError:
            LOGGER.error("%s not provided in service call.", CONF_BEFORE)
            return
        try:
            _after = set_time_at_date(
                local_now, dt_util.parse_time(call.data[CONF_AFTER])
            )
        except KeyError:
            LOGGER.error("%s not provided in service call.".format(CONF_AFTER))
            return
        LOGGER.debug("Before: %s, After %s", _before, _after)

        await flow(hass, local_now, _before, _after, entity_id)

    hass.services.async_register(DOMAIN, "activate", async_activate)
    # hass.services.async_register(DOMAIN,"do_scene",_activate_scene)
    return True
