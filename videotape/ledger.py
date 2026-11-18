"""A project's ledger.jsonl records render time and money: one line per filmed take, with its price when the call was
paid for, one per paid read of a key's picture, one per paid judgment of a move's frames, and one per pod session.
Each line names its tape, and lines are appended and never rewritten."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from videotape.errors import ScreenplayError, shown


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Ledger:
    """The project's ledger as one tape sees it: it appends lines that name the tape, and reads only those."""

    path: Path
    tape: str

    def append(self, line: dict) -> None:
        with self.path.open("a") as file:
            file.write(json.dumps({**line, "tape": self.tape}, sort_keys=True) + "\n")

    def lines(self) -> list[dict]:
        """The tape's lines, in order: VT410 at a line of the ledger that is not JSON."""
        if not self.path.exists():
            return []
        lines = []
        for number, text in enumerate(self.path.read_text().splitlines(), 1):
            if not text:
                continue
            try:
                lines.append(json.loads(text))
            except json.JSONDecodeError as error:
                raise ScreenplayError("VT410", f"{shown(self.path)}:{number}", f"is not JSON: {error}",
                                      "delete the line, or mend it; the lines are appended and never rewritten, so the "
                                      "rest stand, and what the line's call billed no longer counts toward the tape's "
                                      "cap") from None
        return [line for line in lines if line["tape"] == self.tape]

    def spent(self) -> float:
        """What the tape's lines billed, summed before any rounding, where totals rounds to the cent."""
        return sum(line.get("usd") or 0.0 for line in self.lines())

    def totals(self) -> dict:
        lines = self.lines()
        takes = [line for line in lines if line["kind"] == "take"]
        pods = [line for line in lines if line["kind"] == "pod"]
        return {
            "takes": len(takes),
            "gpu_seconds": round(sum((line["seconds"] for line in takes), 0.0), 1),
            "pods": len(pods),
            "pod_hours": round(sum((line["seconds"] for line in pods), 0.0) / 3600, 3),
            "reads": sum(line["kind"] == "read" for line in lines),
            "judgments": sum(line["kind"] == "judgment" for line in lines),
            "usd": round(self.spent(), 2),
        }


def of(project: Path, tape: Path) -> Ledger:
    """The ledger of the project for this tape, which it names by its path from the project."""
    project, tape = project.resolve(), tape.resolve()
    return Ledger(project / "ledger.jsonl", tape.relative_to(project).as_posix() if tape.is_relative_to(project) else str(tape))
