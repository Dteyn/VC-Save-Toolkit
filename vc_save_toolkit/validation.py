"""Small validation helpers shared by the UI preflight and tests."""

from __future__ import annotations

import math


def parse_int(text: str, minimum: int, maximum: int) -> int:
    """Parse a base-10 integer and enforce the exact encodable range."""
    try:
        value = int(str(text).strip())
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a whole number.") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"Enter a value from {minimum} to {maximum}.")
    return value


def parse_float(text: str) -> float:
    """Parse a finite floating-point value."""
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a decimal number.") from error
    if not math.isfinite(value):
        raise ValueError("Enter a finite number.")
    return value


def parse_bool(text: str) -> bool:
    """Parse the friendly boolean spellings accepted by the statistics editor."""
    value = str(text).strip().lower()
    if value in {"1", "yes", "true", "on"}:
        return True
    if value in {"0", "no", "false", "off"}:
        return False
    raise ValueError("Choose Yes or No.")
