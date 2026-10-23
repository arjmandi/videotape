"""What `videotape check` reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Diagnostic:
    level: Literal["error", "warning"]
    code: str
    message: str
    at: str | None = None
    """Where: `tape`, `tape/frame`, a handler (`sign_in()`), or a record (`Deal`)."""

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"level": self.level, "code": self.code, "message": self.message}
        if self.at:
            out["at"] = self.at
        return out

    def __str__(self) -> str:
        where = f" {self.at}:" if self.at else ""
        return f"{self.level} [{self.code}]{where} {self.message}"


def error(code: str, message: str, at: str | None = None) -> Diagnostic:
    return Diagnostic("error", code, message, at)


def warning(code: str, message: str, at: str | None = None) -> Diagnostic:
    return Diagnostic("warning", code, message, at)
