import asyncio
from datetime import datetime, time
from unittest.mock import Mock

import homeassistant.util.dt as dt_util
import pytest

# from .common import async_test_home_assistant
from common import async_test_home_assistant
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.util.dt import UTC
from voluptuous import Schema

from time_slot_solar_event import (
    async_setup,
    DOMAIN,
    ATTR_BEFORE,
    ATTR_AFTER,
    flow,
    set_time_at_date,
    get_solar_event,
    ATTR_SOLAR_EVENT,
    SERVICE_SCHEMA)


@pytest.fixture
def hass():
    """Fixture to provide a test instance of HASS."""
    loop = asyncio.get_event_loop()
    hass = loop.run_until_complete(async_test_home_assistant(loop))

    # services = Mock()
    # async_register = Mock()
    # services.async_register = async_register
    # hass.services = services

    yield hass


@pytest.fixture
def loop():
    loop = asyncio.get_event_loop()
    return loop


@pytest.fixture
def config_data():
    return Schema({})


@pytest.fixture
def do_fake_time(monkeypatch):
    def make_do(hour, minute, timezone=None):
        if timezone is None:
            timezone = UTC

        def fake_now():

            return datetime(
                year=2018,
                month=1,
                day=1,
                hour=hour,
                minute=minute,
                tzinfo=timezone,
            )

        monkeypatch.setattr("homeassistant.util.dt.now", fake_now)
        return fake_now()

    return make_do

def test_service_data():
    #todo: how to properly test that something does NOT raise an exception ?
    data = {"before":"8:00","after":"6:00","entity_id":"scene_a","solar_event":"dusk"}
    SERVICE_SCHEMA(data)



def test_async_setup(hass, monkeypatch, config_data, do_fake_time, loop):
    fake_now = do_fake_time(6, 5)

    mock_flow = Mock()

    async def mockflow(*args, **kwargs):
        mock_flow(*args, **kwargs)

    monkeypatch.setattr("time_slot_solar_event.flow", mockflow)

    val = loop.run_until_complete(async_setup(hass, config_data))
    assert val is True

    activate_service = hass.services.has_service(DOMAIN, "activate")
    assert activate_service is True

    val = loop.run_until_complete(
        hass.services.async_call(
            DOMAIN,
            "activate",
            service_data={"after": "20:00", "before": "21:00"},
        )
    )
    mock_flow.assert_not_called()

    before = set_time_at_date(dt_util.now(), time(hour=21))
    after = set_time_at_date(dt_util.now(), time(hour=20))

    try:
        loop.run_until_complete(
            hass.services.async_call(
                DOMAIN,
                "activate",
                service_data={
                    ATTR_AFTER: "20:00",
                    ATTR_BEFORE: "21:00",
                    ATTR_ENTITY_ID: "abv",
                    ATTR_SOLAR_EVENT: "dawn",
                },
            )
        )
    except Exception as err:
        pass
    mock_flow.assert_called_once_with(
        hass, fake_now, before, after, "abv", "dawn"
    )


@pytest.fixture
def fake_activate_scene(monkeypatch):
    fake_scene = Mock()

    async def _fake_activate_scene(*args, **kwargs):
        fake_scene(*args, **kwargs)

    monkeypatch.setattr(
        "time_slot_solar_event.activate_scene", _fake_activate_scene
    )
    return fake_scene


def test_flow_dawn_later_than_before(
    hass, do_fake_time, fake_activate_scene, loop
):
    fake_local_now = do_fake_time(6, 5, hass.config.time_zone)

    before = set_time_at_date(fake_local_now, time(hour=7))
    after = set_time_at_date(fake_local_now, time(hour=6))

    scene_id = "scene_a"

    loop.run_until_complete(
        flow(hass, fake_local_now, before, after, scene_id, "dawn")
    )

    fake_activate_scene.assert_called_once_with(hass, scene_id, before)


def test_flow_dawn_between_now_and_before(
    hass, do_fake_time, fake_activate_scene, loop
):
    fake_local_now = do_fake_time(6, 5, hass.config.time_zone)

    before = set_time_at_date(fake_local_now, time(hour=9))
    after = set_time_at_date(fake_local_now, time(hour=6))
    scene_id = "scene_a"

    next_dawn = get_solar_event("dawn", fake_local_now, hass)

    loop.run_until_complete(
        flow(hass, fake_local_now, before, after, scene_id, "dawn")
    )

    fake_activate_scene.assert_called_once_with(hass, scene_id, next_dawn)


def test_flow_dawn_earlier_than_now(
    hass, do_fake_time, fake_activate_scene, loop
):
    fake_local_now = do_fake_time(9, 5, hass.config.time_zone)

    before = set_time_at_date(fake_local_now, time(hour=10))
    after = set_time_at_date(fake_local_now, time(hour=9))
    scene_id = "scene_a"

    loop.run_until_complete(
        flow(hass, fake_local_now, before, after, scene_id, "dawn")
    )

    fake_activate_scene.assert_called_once_with(hass, scene_id)
