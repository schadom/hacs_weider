"""Plausibility limits for WT16 readings."""

# The device reports a placeholder value, such as 3276.7 or 6553.5, for a
# temperature sensor that is not connected. Readings outside this range are
# treated as unknown. The range covers outdoor temperatures down to -45 °C and
# the hot gas temperature of the refrigerant circuit.
MIN_TEMPERATURE = -45.0
MAX_TEMPERATURE = 150.0


def plausible_temperature(value: float | None) -> float | None:
    """Return the temperature, or None if it is a placeholder value."""
    if value is None or MIN_TEMPERATURE <= value <= MAX_TEMPERATURE:
        return value
    return None
