"""A schedule component to activate a scene based on time and solar event:

An automation example:

trigger:

"""
import logging
from datetime import datetime, time
from typing import Optional

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers.event import (
    async_track_point_in_time,
)
from homeassistant.helpers.sun import get_astral_event_next
from homeassistant.util.dt import UTC

LOGGER = logging.getLogger(__name__)


DOMAIN = "time_slot_solar_event"

ATTR_BEFORE = "before"
ATTR_AFTER = "after"
ATTR_SOLAR_EVENT = "solar_event"

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.string,
        vol.Required(ATTR_BEFORE): cv.string,
        vol.Required(ATTR_AFTER): cv.string,
        vol.Required(ATTR_SOLAR_EVENT): vol.In("dawn", "dusk"),
    }
)


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


def get_solar_event(solar_event, local_now, hass):
    """Returns the next occurring solar event. Local time."""
    current_day_utc = dt_util.as_utc(local_now).date()
    start_of_day_utc = datetime.combine(
        current_day_utc, time(hour=0, minute=0), tzinfo=UTC
    )
    next_dawn = dt_util.as_local(
        get_astral_event_next(
            hass, solar_event, utc_point_in_time=start_of_day_utc
        )
    )
    return next_dawn


async def flow(
    hass,
    now: datetime,
    before: datetime,
    after: datetime,
    scene_id: str,
    solar_event: str,
):
    if after < now < before:
        LOGGER.info("Morning scenario")

        next_solar_event = get_solar_event(solar_event,now, hass)

        LOGGER.debug("next %s: %s",solar_event, next_solar_event)

        if now >= next_solar_event:
            LOGGER.info("%s has passed. Activating scene.",solar_event)
            # activate the up scene.
            await activate_scene(hass, scene_id)

        elif next_solar_event > before:
            LOGGER.info("Scheduling scene activation at morning end.")
            await activate_scene(hass, scene_id, before)

        else:
            LOGGER.info("Scheduling scene activation at %s",solar_event)
            # schedule the shade activation at dawn
            await activate_scene(hass, scene_id, next_solar_event)
    else:
        LOGGER.debug("Current time outside morning time frame.")


async def async_setup(hass, config):
    """Setup the component."""

    async def async_activate(call):
        LOGGER.debug("Service activated")

        entity_id = call.data[ATTR_ENTITY_ID]
        solar_event=call.data[ATTR_SOLAR_EVENT]
        local_now = dt_util.now()

        _before = set_time_at_date(
            local_now, dt_util.parse_time(call.data[ATTR_BEFORE])
        )

        _after = set_time_at_date(
            local_now, dt_util.parse_time(call.data[ATTR_AFTER])
        )

        LOGGER.debug("Before: %s, After %s", _before, _after)

        await flow(hass, local_now, _before, _after, entity_id,solar_event)

    hass.services.async_register(
        DOMAIN, "activate", async_activate, schema=SERVICE_SCHEMA
    )
    return True
