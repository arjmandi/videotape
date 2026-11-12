"""A project's ledger.jsonl records render time and money: one line per filmed take, with its price when the call was
paid for, and one per pod session. Each line names its tape, and lines are appended and never rewritten."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


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
        if not self.path.exists():
            return []
        lines = [json.loads(line) for line in self.path.read_text().splitlines() if line]
        return [line for line in lines if line["tape"] == self.tape]

    def totals(self) -> dict:
        lines = self.lines()
        takes = [line for line in lines if line["kind"] == "take"]
        pods = [line for line in lines if line["kind"] == "pod"]
        return {
            "takes": len(takes),
            "gpu_seconds": round(sum((line["seconds"] for line in takes), 0.0), 1),
            "pods": len(pods),
            "pod_hours": round(sum((line["seconds"] for line in pods), 0.0) / 3600, 3),
            "usd": round(sum((line.get("usd", 0.0) for line in takes + pods), 0.0), 2),
        }


def of(project: Path, tape: Path) -> Ledger:
    """The ledger of the project for this tape, which it names by its path from the project."""
    project, tape = project.resolve(), tape.resolve()
    return Ledger(project / "ledger.jsonl", tape.relative_to(project).as_posix() if tape.is_relative_to(project) else str(tape))
