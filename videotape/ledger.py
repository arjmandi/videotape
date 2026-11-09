"""tape/ledger.jsonl records GPU time and money: one line per filmed take and one per pod session, appended and never rewritten."""

import json
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append(tape: Path, line: dict) -> None:
    with (tape / "ledger.jsonl").open("a") as file:
        file.write(json.dumps(line, sort_keys=True) + "\n")


def read(tape: Path) -> list[dict]:
    path = tape / "ledger.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []


def totals(lines: list[dict]) -> dict:
    takes = [line for line in lines if line["kind"] == "take"]
    pods = [line for line in lines if line["kind"] == "pod"]
    return {
        "takes": len(takes),
        "gpu_seconds": round(sum((line["seconds"] for line in takes), 0.0), 1),
        "pods": len(pods),
        "pod_hours": round(sum((line["seconds"] for line in pods), 0.0) / 3600, 3),
        "usd": round(sum((line["usd"] for line in pods), 0.0), 2),
    }
