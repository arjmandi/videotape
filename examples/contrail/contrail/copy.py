"""How Contrail's values read on screen."""

import hashlib
from datetime import date, time

from contrail.data import Flight


def money(dollars: int) -> str:
    return f"${dollars:,}"


def clock(at: time) -> str:
    return at.strftime("%-I:%M %p")


def times(flight: Flight) -> str:
    return f"{clock(flight.departs)} to {clock(flight.arrives)}"


def duration(flight: Flight) -> str:
    hours, minutes = divmod(flight.minutes, 60)
    return f"{hours}h {minutes:02d}m"


def stops(flight: Flight) -> str:
    return "Nonstop" if flight.stops == 0 else f"{flight.stops} stop"


def long_day(day: date) -> str:
    return day.strftime("%A, %B %-d")


def short_day(day: date) -> str:
    return day.strftime("%b %-d")


def joined(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])}, and {names[-1]}"


def confirmation(flight: Flight) -> str:
    """A demo confirmation code, the same every time for the same flight."""
    return hashlib.sha256(f"{flight.number} {flight.day}".encode()).hexdigest()[:6].upper()
