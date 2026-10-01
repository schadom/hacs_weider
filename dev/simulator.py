"""Synthetic WT16 Modbus TCP device for local integration testing."""

import asyncio
import logging
import os

from pymodbus.server import StartAsyncTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice


def create_device() -> SimDevice:
    """Build independent input, holding and discrete-input address spaces."""
    temperatures = [200] * 32
    for address, value in {
        13: 425, 14: 350, 15: 85, 16: 320, 25: 345, 26: 290,
        27: 100, 28: 65, 29: 50, 31: 35, 33: 400, 37: 680, 44: 1234,
    }.items():
        temperatures[address - 13] = value
    inputs = [
        SimData(13, values=temperatures, datatype=DataType.REGISTERS),
        SimData(724, values=215, datatype=DataType.REGISTERS),
        SimData(736, values=50, datatype=DataType.REGISTERS),
        SimData(60164, values=[0, 120], datatype=DataType.REGISTERS),
        SimData(60168, values=[0, 30], datatype=DataType.REGISTERS),
        SimData(63000, count=16, values=0, datatype=DataType.REGISTERS),
    ]
    settings = [
        SimData(1, values=450, datatype=DataType.REGISTERS),
        SimData(723, values=220, datatype=DataType.REGISTERS),
    ]
    discrete = [False] * 720
    for address in (45, 69, 679, 680, 681):
        discrete[address] = True
    return SimDevice(
        id=1,
        simdata=(
            [SimData(0, values=[False] * 16, datatype=DataType.BITS)],
            [SimData(0, values=discrete, datatype=DataType.BITS)],
            settings,
            inputs,
        ),
    )


async def main() -> None:
    """Serve synthetic data; writes affect only in-memory target registers."""
    host = os.environ.get("MODBUS_HOST", "127.0.0.1")
    port = int(os.environ.get("MODBUS_PORT", "5020"))
    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).info("WT16 simulator: %s:%s, unit 1", host, port)
    await StartAsyncTcpServer(create_device(), address=(host, port))


if __name__ == "__main__":
    asyncio.run(main())