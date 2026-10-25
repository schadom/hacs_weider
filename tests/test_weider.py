"""Regression tests using HA's shared connection and real Modbus models."""

from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import PropertyMock, patch

from modbus_connection import ModbusError
from modbus_connection.exceptions import IllegalDataAddressError
from modbus_connection.mock import MockModbusConnection
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from weider_modbus import WeiderWT16

from homeassistant.components.modbus.connection import DATA_MODBUS_CONNECTIONS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.weider.climate import DESCRIPTIONS
from custom_components.weider.config_flow import STEP_USER
from custom_components.weider.const import DOMAIN, FAILED_POLL_TOLERANCE
from custom_components.weider.binary_sensor import BINARY_SENSORS
from custom_components.weider.sensor import SENSORS

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")
CONNECTION_DATA = {"host": "pump.local", "port": 502, "unit_id": 1}
HOT_WATER = "sensor.weider_wt16_hot_water_temperature"
# Entities that are disabled by default.
RESERVE_SENSORS = {"reserve_temperature_1", "reserve_temperature_2", "reserve_temperature_3"}
RESERVE_BINARY_SENSORS = {"reserve_1", "reserve_2", "reserve_3", "cooling_output", "reserve_5", "reserve"}


@pytest.fixture
def enable_all_entities():
    """Create every entity enabled, including the disabled-by-default ones."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        new_callable=PropertyMock,
        return_value=True,
    ):
        yield


@pytest.fixture(autouse=True)
def no_retry_delay():
    """Retry failed polls immediately."""
    with patch("custom_components.weider.coordinator.RETRY_DELAY", timedelta(0)):
        yield


@pytest.fixture
def connection():
    """Replace only the wire transport, retaining HA's connection ownership."""
    connection = MockModbusConnection()
    unit = connection.for_unit(1)
    unit.input.update({12: 215, 13: 425, 44: 1234, 60164: [1, 2]})
    unit.holding.update({1: 450, 723: 220})
    unit.discrete[679] = True
    with patch(
        "homeassistant.components.modbus.connection.ModbusConnection",
        return_value=connection,
    ):
        yield connection


def make_entry(hass, **kwargs):
    """Register a Weider config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        # An installation from before 1.4.0 keeps its stored title and entity IDs.
        title=kwargs.pop("title", "Weider WT16"),
        data=kwargs.pop("data", CONNECTION_DATA),
        unique_id=kwargs.pop("unique_id", "pump.local_502_1"),
        **kwargs,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize("probe_only", [False, True])
async def test_setup_with_unsupported_input(hass, connection, probe_only):
    unit = connection.for_unit(1)
    read = unit.read_discrete_inputs

    async def read_supported(address, count):
        if address <= 690 < address + count:
            raise IllegalDataAddressError()
        return await read(address, count)

    with patch.object(unit, "read_discrete_inputs", side_effect=read_supported):
        if probe_only:
            with patch("custom_components.weider.async_setup_entry", return_value=True):
                result = await hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": "user"}, data=CONNECTION_DATA,
                )
                await hass.async_block_till_done()
            assert result["type"] is FlowResultType.CREATE_ENTRY
            assert hass.data[DATA_MODBUS_CONNECTIONS] == {}
            return
        entry = make_entry(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert not any("four_way_valve" in state.entity_id
                       for state in hass.states.async_all("binary_sensor"))
        assert len(hass.states.async_all("binary_sensor")) == 19
        assert entry.runtime_data.device.digital_inputs.compressor is True
        await entry.runtime_data.async_refresh()
        assert entry.runtime_data.last_update_success
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unsupported_room_target_creates_no_room_entities(hass, connection):
    unit = connection.for_unit(1)
    unit.fail_read(723, IllegalDataAddressError(), register_type="holding")
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("climate.weider_wt16_room_temperature") is None
    assert hass.states.get("climate.weider_wt16_hot_water_temperature").state == "heat"
    assert hass.states.get("sensor.weider_wt16_room_target_temperature") is None
    assert hass.states.get("sensor.weider_wt16_room_temperature") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.usefixtures("enable_all_entities")
async def test_unsupported_measurement_creates_no_entity(hass, connection, caplog):
    import logging

    unit = connection.for_unit(1)
    unit.fail_read(736, IllegalDataAddressError(), register_type="input")
    caplog.set_level(logging.INFO)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.weider_wt16_mixer_position") is None
    assert len(hass.states.async_all("sensor")) == 27
    records = [r for r in caplog.records if "Skipping unsupported" in r.getMessage()]
    assert records
    assert {r.levelno for r in records} == {logging.INFO}
    assert "mixer_position" in records[0].getMessage()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unsupported_sg_ready_inputs_create_no_mode_sensor(hass, connection):
    unit = connection.for_unit(1)
    read = unit.read_discrete_inputs

    async def read_supported(address, count):
        if address <= 707 < address + count:
            raise IllegalDataAddressError()
        return await read(address, count)

    with patch.object(unit, "read_discrete_inputs", side_effect=read_supported):
        entry = make_entry(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.weider_wt16_sg_ready_mode") is None
        assert hass.states.get("binary_sensor.weider_wt16_sg_ready_2") is None
        assert hass.states.get("binary_sensor.weider_wt16_sg_ready_1") is not None
        assert await hass.config_entries.async_unload(entry.entry_id)

def test_connection_schema():
    assert STEP_USER({"host": "pump.local"}) == CONNECTION_DATA


def test_connection_schema_serializes_for_frontend():
    from probatio.codecs.fields import to_field_list

    from homeassistant.helpers import config_validation as cv

    fields = to_field_list(STEP_USER, custom_serializer=cv.custom_serializer)
    assert [field["name"] for field in fields] == ["host", "port", "unit_id"]


@pytest.mark.parametrize("data", [
    {"host": ""}, {"host": "pump", "port": 0},
    {"host": "pump", "port": 65536}, {"host": "pump", "unit_id": 0},
    {"host": "pump", "unit_id": 248},
])
def test_invalid_connection_schema(data):
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        STEP_USER(data)


async def test_config_flow_releases_probe(hass, connection):
    with patch("custom_components.weider.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"},
            data={**CONNECTION_DATA, "host": " PUMP.LOCAL "},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == CONNECTION_DATA
    assert result["result"].unique_id == "pump.local_502_1"
    assert hass.data[DATA_MODBUS_CONNECTIONS] == {}
    assert not connection.connected


async def test_duplicate_does_not_probe(hass, connection):
    make_entry(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data=CONNECTION_DATA,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert not connection.for_unit(1).read_events


async def test_failed_probe_releases_connection(hass, connection):
    connection.for_unit(1).fail_requests(ModbusError("offline"))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data=CONNECTION_DATA,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert hass.data[DATA_MODBUS_CONNECTIONS] == {}
    assert not connection.connected


async def test_blank_host_does_not_probe(hass, connection):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"},
        data={**CONNECTION_DATA, "host": "   "},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert not connection.for_unit(1).read_events


async def test_new_entry_title(hass, connection):
    """A new installation is named "Weider"."""
    with patch("custom_components.weider.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data=CONNECTION_DATA,
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Weider"


async def test_new_entry_device_and_entity_ids(hass, connection):
    """The device model comes from the library; entity IDs follow the title."""
    from homeassistant.helpers import device_registry as dr

    entry = make_entry(hass, title="Weider")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert (device.name, device.manufacturer, device.model) == ("Weider", "Weider", "WT16")
    assert hass.states.get("sensor.weider_hot_water_temperature").state == "42.5"
    assert hass.states.get("sensor.weider_wt16_hot_water_temperature") is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_second_heat_pump_gets_distinct_name(hass, connection):
    from homeassistant.helpers import device_registry as dr

    first = make_entry(hass)
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={**CONNECTION_DATA, "unit_id": 2},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Weider (pump.local, unit 2)"
    second = result["result"]
    assert second.state is ConfigEntryState.LOADED
    registry = dr.async_get(hass)
    names = {
        device.name
        for entry in (first, second)
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert names == {"Weider WT16", "Weider (pump.local, unit 2)"}
    assert await hass.config_entries.async_unload(first.entry_id)
    assert await hass.config_entries.async_unload(second.entry_id)

async def test_reconfigure_legacy_entry(hass, connection):
    entry = make_entry(hass, data={"connection": "old-entry", "unit_id": 1})
    original_id = entry.entry_id
    with patch.object(hass.config_entries, "async_schedule_reload") as reload_entry:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id},
            data=CONNECTION_DATA,
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.entry_id == original_id
    assert entry.data == CONNECTION_DATA
    reload_entry.assert_called_once_with(entry.entry_id)


@pytest.mark.usefixtures("enable_all_entities")
@pytest.mark.parametrize("language", ["en", "de"])
async def test_entity_translations(hass, connection, language):
    integration_path = Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN
    translations = json.loads(
        (integration_path / "translations" / f"{language}.json").read_text(encoding="utf-8")
    )["entity"]
    source = json.loads((integration_path / "strings.json").read_text(encoding="utf-8"))["entity"]
    descriptions = {"sensor": SENSORS, "binary_sensor": BINARY_SENSORS, "climate": DESCRIPTIONS}
    assert translations.keys() == source.keys() == descriptions.keys()
    hass.config.language = language
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for platform, points in descriptions.items():
        assert translations[platform].keys() == source[platform].keys() == {point.key for point in points}
        for point in points:
            if platform == "climate":
                assert source[platform][point.key]["name"] == point.name
            if language == "en":
                assert translations[platform][point.key] == source[platform][point.key]
            key = f"climate_{point.key}" if platform == "climate" else point.key
            entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
            assert entity_id is not None
            state = hass.states.get(entity_id)
            assert state is not None
            name = translations[platform][point.key]["name"]
            assert name
            assert state.attributes["friendly_name"] == f"Weider WT16 {name}"
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.usefixtures("enable_all_entities")
async def test_sensor_state_classes(hass, connection):
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for description in SENSORS:
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{description.key}")
        state_class = hass.states.get(entity_id).attributes.get("state_class")
        expected = None if description.key in ("active_error", "sg_ready_mode") else "measurement"
        assert state_class == expected, description.key
    assert await hass.config_entries.async_unload(entry.entry_id)

@pytest.mark.parametrize(("utility_block", "sg_ready_1", "sg_ready_2", "expected"), [
    (False, False, False, "bz2_normal"),
    (False, False, True, "bz3_increased"),
    (False, True, False, "bz4_start"),
    (False, True, True, "bz2_normal"),
    (True, False, False, "bz1_utility_block"),
    (True, True, True, "bz1_utility_block"),
])
async def test_sg_ready_mode(hass, connection, utility_block, sg_ready_1, sg_ready_2, expected):
    connection.for_unit(1).discrete.update(
        {705: utility_block, 706: sg_ready_1, 707: sg_ready_2}
    )
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.weider_wt16_sg_ready_mode")
    assert state.state == expected
    assert state.attributes["options"] == [
        "bz1_utility_block", "bz2_normal", "bz3_increased", "bz4_start",
    ]
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("language", ["en", "de"])
def test_sg_ready_mode_states_translated(language):
    from custom_components.weider.sensor import SG_READY_OPTIONS

    integration_path = Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN
    translations = json.loads(
        (integration_path / "translations" / f"{language}.json").read_text(encoding="utf-8")
    )
    states = translations["entity"]["sensor"]["sg_ready_mode"]["state"]
    assert set(states) == set(SG_READY_OPTIONS)
    assert all(label.startswith(key[:3].upper()) for key, label in states.items())

@pytest.mark.usefixtures("enable_all_entities")
async def test_setup_poll_recovery_and_unload(hass, connection):
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert len(hass.states.async_all("sensor")) == 28
    assert len(hass.states.async_all("binary_sensor")) == 20
    assert len(hass.states.async_all("climate")) == 2
    coordinator = entry.runtime_data
    unit = connection.for_unit(1)
    unit.fail_requests(ModbusError("offline"))
    with patch.object(hass.config_entries, "async_schedule_reload") as reload_entry:
        for _ in range(FAILED_POLL_TOLERANCE - 1):
            await coordinator.async_refresh()
            await hass.async_block_till_done()
            assert coordinator.last_update_success
            assert hass.states.get(HOT_WATER).state == "42.5"
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert not coordinator.last_update_success
        assert hass.states.get(HOT_WATER).state == "unavailable"
        connection.simulate_connection_lost()
        unit.fail_requests(None)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert coordinator.last_update_success
        assert coordinator.failed_polls == 0
        assert hass.states.get(HOT_WATER).state == "42.5"
        reload_entry.assert_not_called()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert hass.data[DATA_MODBUS_CONNECTIONS] == {}
    assert not connection.connected


@pytest.mark.usefixtures("socket_enabled")
async def test_simulator_tcp_read_and_write(unused_tcp_port):
    from modbus_connection import ModbusTcpParams
    from modbus_connection.tmodbus import ModbusConnection
    from pymodbus.server import ModbusTcpServer

    from dev.simulator import create_device

    server = ModbusTcpServer(create_device(), address=("127.0.0.1", unused_tcp_port))
    await server.serve_forever(background=True)
    connection = ModbusConnection(ModbusTcpParams(host="127.0.0.1", port=unused_tcp_port))
    try:
        device = WeiderWT16(connection.for_unit(1))
        await device.async_update()
        assert device.measurements.hot_water_temperature == 42.5
        assert device.digital_inputs.compressor is True
        assert device.digital_inputs.remote_fault is False
        await device.settings.write("room_target_temperature", 23.5)
        await device.async_update()
        assert device.settings.room_target_temperature == 23.5
    finally:
        await connection.close()
        await server.shutdown()


async def test_setup_failure_releases_connection(hass, connection):
    connection.for_unit(1).fail_requests(ModbusError("offline"))
    entry = make_entry(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.data[DATA_MODBUS_CONNECTIONS] == {}


@pytest.mark.parametrize(("raw", "expected"), [
    (215, "21.5"), (1500, "150.0"), (1501, "unknown"), (32767, "unknown"),
])
async def test_implausible_room_temperature(hass, connection, raw, expected):
    connection.for_unit(1).input[12] = raw
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.weider_wt16_room_temperature").state == expected
    climate = hass.states.get("climate.weider_wt16_room_temperature")
    current = climate.attributes.get("current_temperature")
    assert current == (None if expected == "unknown" else float(expected))
    assert await hass.config_entries.async_unload(entry.entry_id)

async def test_legacy_entry_has_actionable_error(hass, connection):
    entry = make_entry(hass, data={"connection": "old-entry", "unit_id": 1})
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert "Reconfigure" in entry.reason
    assert not connection.connected


def _ascii_words(text: str) -> list[int]:
    raw = text.encode("ascii").ljust(32, b"\x00")
    return [raw[i] << 8 | raw[i + 1] for i in range(0, 32, 2)]


@pytest.mark.parametrize(("raw", "expected"), [
    ("", "none"), (" " * 32, "none"), ("E12 HD", "E12 HD"),
    ("  E12   HD  ", "E12 HD"), ("\x00\x00E05", "E05"),
])
async def test_active_error_text(hass, connection, raw, expected):
    words = _ascii_words(raw)
    connection.for_unit(1).input.update(dict(zip(range(63000, 63016), words)))
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.weider_wt16_active_error").state == expected
    assert await hass.config_entries.async_unload(entry.entry_id)

async def test_climate_write_failure_is_ha_error(hass, connection):
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    climate = next(state for state in hass.states.async_all("climate")
                   if "hot_water" in state.entity_id)
    connection.for_unit(1).fail_write(1, ModbusError("write rejected"))
    with pytest.raises(HomeAssistantError, match="write rejected"):
        await hass.services.async_call(
            "climate", "set_temperature",
            {"entity_id": climate.entity_id, "temperature": 47.5}, blocking=True,
        )
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_climate_write_updates_target(hass, connection):
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "climate", "set_temperature",
        {"entity_id": "climate.weider_wt16_hot_water_temperature", "temperature": 47.5},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("climate.weider_wt16_hot_water_temperature").attributes["temperature"] == 47.5
    assert hass.states.get("sensor.weider_wt16_hot_water_target_temperature").state == "47.5"
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(("compressor", "hot_water_pump", "heating_pump", "hot_water", "room"), [
    (True, True, False, "heating", "idle"),
    (True, False, True, "idle", "heating"),
    (False, True, True, "idle", "idle"),
])
async def test_climate_hvac_action(
    hass, connection, compressor, hot_water_pump, heating_pump, hot_water, room,
):
    connection.for_unit(1).discrete.update(
        {679: compressor, 685: hot_water_pump, 680: heating_pump}
    )
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("climate.weider_wt16_hot_water_temperature").attributes["hvac_action"] == hot_water
    assert hass.states.get("climate.weider_wt16_room_temperature").attributes["hvac_action"] == room
    assert await hass.config_entries.async_unload(entry.entry_id)

async def test_shared_connection_survives_one_entry_unload(hass, connection):
    first = make_entry(hass)
    assert await hass.config_entries.async_setup(first.entry_id)
    second = make_entry(hass, data={**CONNECTION_DATA, "unit_id": 2}, unique_id="pump.local_502_2")
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    assert len(hass.data[DATA_MODBUS_CONNECTIONS]) == 1
    assert await hass.config_entries.async_unload(first.entry_id)
    assert connection.connected
    await second.runtime_data.async_refresh()
    assert second.runtime_data.last_update_success
    assert await hass.config_entries.async_unload(second.entry_id)
    assert not connection.connected
    assert hass.data[DATA_MODBUS_CONNECTIONS] == {}

async def test_connection_reset_is_retried_within_poll(hass, connection):
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    device = coordinator.device
    update = device.async_update
    calls = []

    async def reset_once():
        calls.append(None)
        if len(calls) == 1:
            connection.simulate_connection_lost()
            raise ConnectionResetError(104, "Connection reset by peer")
        await update()

    connection.for_unit(1).input[13] = 500
    with patch.object(device, "async_update", side_effect=reset_once):
        await coordinator.async_refresh()
    assert len(calls) == 2
    assert coordinator.last_update_success
    assert coordinator.failed_polls == 0
    assert device.measurements.hot_water_temperature == 50
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_failed_poll_counter_resets_after_success(hass, connection):
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    unit = connection.for_unit(1)
    for _ in range(3):
        unit.fail_requests(ModbusError("offline"))
        for _ in range(FAILED_POLL_TOLERANCE - 1):
            await coordinator.async_refresh()
            assert coordinator.last_update_success
        unit.fail_requests(None)
        await coordinator.async_refresh()
        assert coordinator.failed_polls == 0
    assert coordinator.last_update_success
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(("register_12", "register_724", "expected"), [
    (215, 0, "21.5"), (0, 225, "22.5"), (0, 0, "unknown"),
])
async def test_room_temperature_entities_use_fallback(
    hass, connection, register_12, register_724, expected
):
    connection.for_unit(1).input.update({12: register_12, 724: register_724})
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.weider_wt16_room_temperature").state == expected
    climate = hass.states.get("climate.weider_wt16_room_temperature")
    current = climate.attributes.get("current_temperature")
    assert current == (None if expected == "unknown" else float(expected))
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_room_temperature_entity_without_register_12(hass, connection):
    """A map that rejects register 12 still gets the room temperature from 724."""
    unit = connection.for_unit(1)
    unit.fail_read(12, IllegalDataAddressError(), register_type="input")
    unit.input[724] = 225
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.weider_wt16_room_temperature").state == "22.5"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_room_temperature_entity_without_room_registers(hass, connection):
    unit = connection.for_unit(1)
    for address in (12, 724):
        unit.fail_read(address, IllegalDataAddressError(), register_type="input")
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.weider_wt16_room_temperature") is None
    climate = hass.states.get("climate.weider_wt16_room_temperature")
    assert climate.attributes.get("current_temperature") is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_reserve_entities_disabled_by_default(hass, connection):
    """The reserve sensors and inputs are registered but disabled by default."""
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for platform, keys in (("sensor", RESERVE_SENSORS), ("binary_sensor", RESERVE_BINARY_SENSORS)):
        for key in keys:
            entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
            assert entity_id is not None, key
            assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
            assert hass.states.get(entity_id) is None
    assert len(hass.states.async_all("sensor")) == 28 - len(RESERVE_SENSORS)
    assert len(hass.states.async_all("binary_sensor")) == 20 - len(RESERVE_BINARY_SENSORS)
    assert hass.states.get("binary_sensor.weider_wt16_compressor") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_enabled_reserve_entity_stays_enabled(hass, connection):
    """An entity enabled by an existing installation keeps working."""
    entry = make_entry(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_reserve_temperature_1",
        config_entry=entry, suggested_object_id="weider_wt16_reserve_sensor_temperature_1",
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_reserve_temperature_1")
    assert registry.async_get(entity_id).disabled_by is None
    assert hass.states.get(entity_id) is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
