"""Turns intent values into JSON: field references, outcomes, phrases, records, and functions."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from .values import Phrase


def name_of(fn: Any) -> str:
    """The name a handler or loader is registered under: its function name."""
    return getattr(fn, "__name__", None) or repr(fn)


def tape_id(tape: Any) -> str:
    """A tape is named by its id or by the tape itself, wherever it is named (Q45, Q50)."""
    if isinstance(tape, str):
        return tape
    if isinstance(getattr(tape, "id", None), str) and hasattr(tape, "frames"):
        return tape.id
    raise TypeError(f"a tape is named by its id or by the tape itself; got {tape!r}")


def encode(value: Any) -> Any:
    """A value written in intent (an option, an argument, a label) as JSON."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Phrase):
        return {"t": value.key, "params": encode(value.params)} if value.params else {"t": value.key}
    if isinstance(value, Enum):
        return encode(value.value)
    if isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, type):
        return value.__name__
    if hasattr(value, "to_json"):
        return value.to_json()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(encode(k)) if not isinstance(k, str) else k: encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    if callable(value):
        return {"handler": name_of(value)}
    raise TypeError(f"cannot put {value!r} in intent JSON")


def encode_target(value: Any) -> Any:
    """What an action, a press, or a select does: an outcome, or the handler that decides."""
    if callable(value) and not hasattr(value, "to_json"):
        return {"handler": name_of(value)}
    return encode(value)
