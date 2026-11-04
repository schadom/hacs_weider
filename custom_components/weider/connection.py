"""How the integration reaches a Weider heat pump."""

from collections.abc import Mapping
from typing import Any

from modbus_connection import ModbusSerialParams, ModbusTcpParams
from weider_modbus import WeiderWT16RTU, WeiderWT16TCP

from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT

from .const import (
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_PARITY,
    CONF_STOPBITS,
    CONF_UNIT_ID,
    CONNECTION_RTU_OVER_TCP,
    CONNECTION_SERIAL,
    CONNECTION_TCP,
)

# A WT16 on either register map.
type WeiderDevice = WeiderWT16TCP | WeiderWT16RTU


def connection_type(data: Mapping[str, Any]) -> str:
    """Return the connection type. Entries from before 1.6.0 use Modbus TCP."""
    return str(data.get(CONF_CONNECTION_TYPE, CONNECTION_TCP))


def connection_params(data: Mapping[str, Any]) -> ModbusTcpParams | ModbusSerialParams:
    """Return the Modbus connection parameters for the entry data."""
    kind = connection_type(data)
    if kind == CONNECTION_SERIAL:
        return ModbusSerialParams(
            device=data[CONF_DEVICE],
            baudrate=int(data[CONF_BAUDRATE]),
            parity=data[CONF_PARITY],
            stopbits=int(data[CONF_STOPBITS]),
        )
    if kind == CONNECTION_RTU_OVER_TCP:
        # RTU frames carried over a TCP socket are a serial link to modbus-connection.
        return ModbusSerialParams(device=f"socket://{data[CONF_HOST]}:{data[CONF_PORT]}")
    return ModbusTcpParams(host=data[CONF_HOST], port=data[CONF_PORT])


def create_device(data: Mapping[str, Any], unit: Any) -> WeiderDevice:
    """Return the device for the register map this connection type uses.

    Modbus TCP uses the Ethernet board's register map. Both RTU connection
    types reach the RS485 port, which uses its own register map.
    """
    if connection_type(data) == CONNECTION_TCP:
        return WeiderWT16TCP(unit)
    return WeiderWT16RTU(unit)


def unique_id(data: Mapping[str, Any]) -> str:
    """Return the unique ID of the heat pump behind this connection."""
    kind = connection_type(data)
    unit_id = data[CONF_UNIT_ID]
    if kind == CONNECTION_SERIAL:
        return f"serial_{data[CONF_DEVICE]}_{unit_id}"
    if kind == CONNECTION_RTU_OVER_TCP:
        return f"rtu_{data[CONF_HOST]}_{data[CONF_PORT]}_{unit_id}"
    # Unchanged from before 1.6.0, so existing entries keep their unique ID.
    return f"{data[CONF_HOST]}_{data[CONF_PORT]}_{unit_id}"


def location(data: Mapping[str, Any]) -> str:
    """Return a short description of where the heat pump is connected.

    A serial port path is long and unreadable as a device name, so a serial
    connection is described by its interface instead.
    """
    if connection_type(data) == CONNECTION_SERIAL:
        return "RS485"
    return str(data[CONF_HOST])
