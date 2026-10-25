"""Constants for Weider."""

from datetime import timedelta

DOMAIN = "weider"
CONF_UNIT_ID = "unit_id"
DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1
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

