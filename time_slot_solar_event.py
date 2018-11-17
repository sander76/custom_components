"""Time slot solar event


A component to activate a scene within a certain time slot and at a certain
solar event.


"""
import logging
from datetime import datetime, time, timedelta
from typing import Optional

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.sun import get_astral_event_next

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
        vol.Required(ATTR_SOLAR_EVENT): vol.In(("dawn", "dusk")),
    }
)


async def activate_scene(
    hass,
    entity_id,
    point_in_time: Optional[datetime] = None,
    service="scene.turn_on",
):
    domain, service_name = service.split(".", 1)

    async def call_service(*args, **kwargs):
        LOGGER.info(
            "%s : Calling service: {}, entity_id: {}".format(
                entity_id, service, entity_id
            )
        )
        await hass.services.async_call(
            domain, service_name, service_data={ATTR_ENTITY_ID: entity_id}
        )

    if point_in_time is not None:
        async_track_point_in_time(hass, call_service, point_in_time)
    else:
        await call_service()


def set_time_at_date(local_now: datetime, time: time):
    tz = local_now.tzinfo
    local_time = tz.localize(datetime.combine(local_now.date(), time))
    return local_time


def get_solar_event(solar_event, local_now, hass):
    """Returns the next occurring solar event. Local time."""
    start_of_day_utc = dt_util.as_utc(
        datetime.combine(local_now.date(), time(hour=0, minute=0))
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
        LOGGER.debug("%s : Trigger is inside time slot.", scene_id)

        next_solar_event = get_solar_event(solar_event, now, hass)

        if now >= next_solar_event:
            LOGGER.info(
                "%s : %s has passed. Activating scene.", scene_id, solar_event
            )
            await activate_scene(hass, scene_id)

        elif next_solar_event > before:
            LOGGER.info(
                "%s : Scheduling at end of time slot: %s", scene_id, before
            )
            await activate_scene(hass, scene_id, before)

        else:
            LOGGER.info(
                "%s : Scheduling at: %s, %s",
                scene_id,
                solar_event,
                next_solar_event,
            )
            await activate_scene(hass, scene_id, next_solar_event)
    else:
        LOGGER.debug("Current time outside morning time frame.")


async def async_setup(hass, config):
    """Setup the component."""

    async def async_activate(call):
        LOGGER.debug("Service activated")

        entity_id = call.data[ATTR_ENTITY_ID]
        solar_event = call.data[ATTR_SOLAR_EVENT]
        local_now = dt_util.now()

        _before = set_time_at_date(
            local_now, dt_util.parse_time(call.data[ATTR_BEFORE])
        )

        _after = set_time_at_date(
            local_now, dt_util.parse_time(call.data[ATTR_AFTER])
        )

        # LOGGER.debug("Before: %s, After %s", _before, _after)

        await flow(hass, local_now, _before, _after, entity_id, solar_event)

    hass.services.async_register(
        DOMAIN, "activate", async_activate, schema=SERVICE_SCHEMA
    )
    return True
