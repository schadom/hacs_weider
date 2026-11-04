"""Constants for Weider."""

from datetime import timedelta

DOMAIN = "weider"
CONF_UNIT_ID = "unit_id"
DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1

# How Home Assistant reaches the heat pump.
CONF_CONNECTION_TYPE = "connection_type"
# Modbus TCP through the Ethernet board.
CONNECTION_TCP = "tcp"
# Modbus RTU on the RS485 port X9, through a serial port.
CONNECTION_SERIAL = "serial"
# Modbus RTU on the RS485 port X9, through a converter on the network.
CONNECTION_RTU_OVER_TCP = "rtu_over_tcp"
CONNECTION_TYPES = [CONNECTION_TCP, CONNECTION_SERIAL, CONNECTION_RTU_OVER_TCP]

# Serial line settings. They must match the controller's Modbus 1 settings.
CONF_BAUDRATE = "baudrate"
CONF_PARITY = "parity"
CONF_STOPBITS = "stopbits"
BAUDRATES = [9600, 19200, 38400, 57600, 115200]
# Parity options shown in the dialog, and the parity they stand for.
PARITIES = {"none": "N", "even": "E", "odd": "O"}
STOPBITS = [1, 2]
DEFAULT_BAUDRATE = 19200
DEFAULT_PARITY = "N"
DEFAULT_STOPBITS = 2
# The heat pump refreshes its Modbus values about once a minute, so polling
# more often only repeats the same values.
SCAN_INTERVAL = timedelta(seconds=60)
# Pause before retrying a failed poll; the shared connection reopens on that request.
RETRY_DELAY = timedelta(seconds=2)
# Consecutive failed polls (each already retried once) before entities become unavailable.
FAILED_POLL_TOLERANCE = 3
# How long a written target is shown before a poll confirms it. The heat pump
# refreshes its Modbus values only about once a minute, so a poll right after a
# write can still return the old target.
PENDING_TARGET_TIMEOUT = timedelta(minutes=3)
# Writable settings whose new value is shown immediately after a write.
TARGET_KEYS = ("hot_water_target_temperature", "room_target_temperature")

