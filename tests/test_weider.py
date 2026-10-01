"""Regression tests using HA's shared connection and real Modbus models."""

from unittest.mock import patch

from modbus_connection import ModbusError
from modbus_connection.exceptions import IllegalDataAddressError, IllegalDataValueError
from modbus_connection.mock import MockModbusConnection, WriteEvent
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.modbus.connection import DATA_MODBUS_CONNECTIONS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from custom_components.weider.config_flow import STEP_USER
from custom_components.weider.const import DOMAIN
from custom_components.weider.vendor.weider_heatpump import WeiderWT16

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")
CONNECTION_DATA = {"host": "pump.local", "port": 502, "unit_id": 1}


@pytest.fixture
def connection():
    """Replace only the wire transport, retaining HA's connection ownership."""
    connection = MockModbusConnection()
    unit = connection.for_unit(1)
    unit.input.update({13: 425, 724: 215, 44: 1234, 60164: [1, 2]})
    unit.holding.update({1: 450, 723: 220})
    unit.discrete_inputs[679] = True
    with patch(
        "homeassistant.components.modbus.connection.ModbusConnection",
        return_value=connection,
    ):
        yield connection


def make_entry(hass, **kwargs):
    """Register a Weider config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=kwargs.pop("data", CONNECTION_DATA),
        unique_id=kwargs.pop("unique_id", "pump.local_502_1"),
        **kwargs,
    )
    entry.add_to_hass(hass)
    return entry


async def test_model_reads_and_fc16_writes(connection):
    unit = connection.for_unit(1)
    device = WeiderWT16(unit)
    await device.async_update()
    assert device.measurements.hot_water_temperature == 42.5
    assert device.measurements.room_temperature == 21.5
    assert device.measurements.volume_flow == 1.234
    assert device.measurements.last_pump_runtime == 65538
    assert device.digital_inputs.compressor is True
    assert device.settings.hot_water_target_temperature == 45
    assert all(event.count <= 50 for event in unit.read_events)
    assert not any(event.address <= 725 < event.address + event.count
                   for event in unit.read_events if event.register_type == "input")
    assert {event.register_type for event in unit.read_events} == {
        "input", "holding", "discrete_input"
    }
    events = []
    unit.on_write(events.append)
    await device.settings.write("hot_water_target_temperature", 47.5)
    assert events == [WriteEvent("holding", 1, [475], 16)]
    await device.async_update()
    assert device.settings.hot_water_target_temperature == 47.5


@pytest.mark.parametrize("previously_supported", [False, True])
async def test_unsupported_digital_inputs(connection, previously_supported):
    unit = connection.for_unit(1)
    device = WeiderWT16(unit)
    unit.discrete_inputs[690] = True
    if previously_supported:
        await device.async_update()
        assert device.digital_inputs.four_way_valve is True
    read = unit.read_discrete_inputs
    rejected = []

    async def read_supported(address, count):
        if any(address <= missing < address + count for missing in (690, 704)):
            rejected.append(address)
            raise IllegalDataAddressError()
        return await read(address, count)

    with patch.object(unit, "read_discrete_inputs", side_effect=read_supported):
        await device.async_update()
        assert device.digital_inputs.four_way_valve is None
        assert device.digital_inputs.heating_block is None
        assert device.digital_inputs.compressor is True
        assert device.digital_inputs.reserve_1 is False
        assert device.digital_inputs.utility_block is False
        first_rejections = list(rejected)
        unit.discrete_inputs[679] = False
        await device.async_update()
        assert device.digital_inputs.compressor is False
        assert rejected == first_rejections
    assert WeiderWT16(unit).digital_inputs.four_way_valve is None
    assert "four_way_valve" in WeiderWT16(unit).digital_inputs.resolved_fields


@pytest.mark.parametrize("error", [
    ModbusError("offline"), TimeoutError("timed out"), IllegalDataValueError(),
])
async def test_digital_input_communication_errors_propagate(connection, error):
    unit = connection.for_unit(1)
    device = WeiderWT16(unit)
    with patch.object(unit, "read_discrete_inputs", side_effect=error):
        with pytest.raises(type(error)):
            await device.async_update()
    assert len(device.digital_inputs.resolved_fields) == 20


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
        valve = next(state for state in hass.states.async_all("binary_sensor")
                     if "four_way_valve" in state.entity_id)
        assert valve.state == "unknown"
        assert entry.runtime_data.device.digital_inputs.compressor is True
        await entry.runtime_data.async_refresh()
        assert entry.runtime_data.last_update_success
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


async def test_setup_poll_recovery_and_unload(hass, connection):
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert len(hass.states.async_all("sensor")) == 27
    assert len(hass.states.async_all("binary_sensor")) == 20
    assert len(hass.states.async_all("climate")) == 2
    coordinator = entry.runtime_data
    connection.for_unit(1).fail_requests(ModbusError("offline"))
    with patch.object(hass.config_entries, "async_schedule_reload") as reload_entry:
        await coordinator.async_refresh()
        assert not coordinator.last_update_success
        connection.simulate_connection_lost()
        connection.for_unit(1).fail_requests(None)
        await coordinator.async_refresh()
        assert coordinator.last_update_success
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


async def test_legacy_entry_has_actionable_error(hass, connection):
    entry = make_entry(hass, data={"connection": "old-entry", "unit_id": 1})
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert "Reconfigure" in entry.reason
    assert not connection.connected


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