import asyncio
from datetime import timedelta, tzinfo
from functools import partial
from unittest.mock import Mock
from typing import Optional
import pytest
import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant, Config
from homeassistant.helpers.sun import get_astral_event_next

from homeassistant.util.unit_system import METRIC_SYSTEM


from morning_scene import (
    async_setup,
    CONFIG_SCHEMA,
    DOMAIN,
    CONF_BEFORE,
    CONF_AFTER,
    flow,
    activate_scene,
    set_time_at_date,
    get_dawn,
)
from datetime import datetime, time

from tests.common import async_test_home_assistant


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
    config = {DOMAIN: {CONF_BEFORE: "8:00", CONF_AFTER: "7:00"}}
    return CONFIG_SCHEMA(config)


@pytest.fixture
def do_fake_time(monkeypatch):
    def make_do(hour, minute, timezone=None):
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


def test_config(config_data):

    conf = config_data[DOMAIN]

    assert isinstance(conf.get(CONF_BEFORE), time)
    assert isinstance(conf.get(CONF_AFTER), time)


def test_async_setup(hass, monkeypatch, config_data, do_fake_time, loop):
    fake_now = do_fake_time(6, 5)

    mock_flow = Mock()

    async def mockflow(*args, **kwargs):
        mock_flow(*args, **kwargs)

    monkeypatch.setattr("morning_scene.flow", mockflow)

    val = loop.run_until_complete(async_setup(hass, config_data))
    assert val is True

    activate_service = hass.services.has_service(DOMAIN, "activate")
    assert activate_service is True

    loop.run_until_complete(
        hass.services.async_call(
            DOMAIN,
            "activate",
            service_data={"after": "20:00", "before": "21:00"},
        )
    )
    mock_flow.assert_not_called()

    before = set_time_at_date(dt_util.now(), time(hour=21))
    after = set_time_at_date(dt_util.now(), time(hour=20))

    loop.run_until_complete(
        hass.services.async_call(
            DOMAIN,
            "activate",
            service_data={
                "after": "20:00",
                "before": "21:00",
                "entity_id": "abv",
            },
        )
    )
    mock_flow.assert_called_once_with(hass, fake_now, before, after, "abv")


@pytest.fixture
def fake_activate_scene(monkeypatch):
    fake_scene = Mock()

    async def _fake_activate_scene(*args, **kwargs):
        fake_scene(*args, **kwargs)

    monkeypatch.setattr("morning_scene.activate_scene", _fake_activate_scene)
    return fake_scene


def test_flow_dawn_later_than_before(
    hass, do_fake_time, fake_activate_scene, loop
):
    fake_local_now = do_fake_time(6, 5, hass.config.time_zone)

    before = set_time_at_date(fake_local_now, time(hour=7))
    after = set_time_at_date(fake_local_now, time(hour=6))

    scene_id = "scene_a"

    loop.run_until_complete(
        flow(hass, fake_local_now, before, after, scene_id)
    )

    fake_activate_scene.assert_called_once_with(hass, scene_id, before)


def test_flow_dawn_between_now_and_before(
    hass, do_fake_time, fake_activate_scene, loop
):
    fake_local_now = do_fake_time(6, 5, hass.config.time_zone)

    before = set_time_at_date(fake_local_now, time(hour=9))
    after = set_time_at_date(fake_local_now, time(hour=6))
    scene_id = "scene_a"

    next_dawn = get_dawn(fake_local_now, hass)

    loop.run_until_complete(
        flow(hass, fake_local_now, before, after, scene_id)
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
        flow(hass, fake_local_now, before, after, scene_id)
    )

    fake_activate_scene.assert_called_once_with(hass, scene_id)
