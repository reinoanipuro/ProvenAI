"""Exact unit conversion. Uses Decimal because binary floats make 1.1 m != 1100 mm."""

from decimal import Decimal

# Canonical unit -> multiplier to the dimension's base unit.
_UNITS: dict[str, dict[str, Decimal]] = {
    "length": {"mm": Decimal(1), "cm": Decimal(10), "m": Decimal(1000)},
    "time": {"s": Decimal(1), "min": Decimal(60), "h": Decimal(3600)},
    "illuminance": {"lx": Decimal(1)},
}

# Spelling as written in a document -> canonical unit.
ALIASES: dict[str, dict[str, str]] = {
    "length": {"mm": "mm", "cm": "cm", "m": "m"},
    "time": {
        "s": "s", "min": "min", "mins": "min", "minute": "min", "minutes": "min",
        "h": "h", "hour": "h", "hours": "h",
    },
    "illuminance": {"lx": "lx", "lux": "lx"},
}


class UnitError(ValueError):
    pass


def to_base(value: Decimal, unit: str, dimension: str) -> Decimal:
    """Convert to the dimension's base unit. Raises UnitError rather than assuming."""
    try:
        return value * _UNITS[dimension][unit]
    except KeyError:
        raise UnitError(f"unit '{unit}' is not valid for dimension '{dimension}'") from None
