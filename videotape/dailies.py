from __future__ import annotations

import json
from dataclasses import asdict
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from videotape import ledger
from videotape.checks import Checks, KeyChecks
from videotape.publish import publish
from videotape.shots import Move

if TYPE_CHECKING:
    from videotape.render import Filmed, Render

STYLE = """
:root { color-scheme: light dark; --bg: #f5f2ec; --card: #fffdf9; --text: #22262a; --muted: #646d75;
  --line: #e4ded3; --pass: #1d7a4a; --fail: #b42318; --kept: #c66a00; --kept-soft: #fff1dc; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #131619; --card: #1b1f23; --text: #e9e6e0; --muted: #98a1a9; --line: #2c3238;
    --pass: #63d297; --fail: #ff8f85; --kept: #ffb457; --kept-soft: #3a2a14; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
header, main { max-width: 1240px; margin: 0 auto; padding: 0 16px; }
header { padding-top: 28px; }
h1 { font-size: 24px; margin: 0 0 4px; }
.summary { color: var(--muted); margin: 0; }
.shot { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px; margin: 20px 0; }
.head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px; }
h2 { font-size: 17px; margin: 0; overflow-wrap: anywhere; }
.badge { font-size: 12px; font-weight: 600; border-radius: 999px; padding: 2px 10px; border: 1px solid var(--line);
  color: var(--muted); white-space: nowrap; }
.badge.rendered { color: var(--pass); border-color: currentColor; }
.badge.kept { color: var(--kept); border-color: currentColor; background: var(--kept-soft); }
.badge.failing { color: var(--fail); border-color: currentColor; }
details { margin-top: 8px; color: var(--muted); font-size: 13px; }
summary { cursor: pointer; }
.takes { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; margin-top: 14px; }
.take { margin: 0; border: 1px solid var(--line); border-radius: 10px; padding: 10px; }
.take.kept { border: 2px solid var(--kept); padding: 9px; }
video, img { display: block; width: 100%; height: auto; aspect-ratio: auto 1280 / 704; border-radius: 6px; background: #000; }
figcaption { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 8px 0 4px; }
.checks { list-style: none; margin: 0; padding: 0; font-size: 13px; }
.checks li { display: grid; grid-template-columns: 1.2em 1fr; column-gap: 4px; padding: 2px 0;
  border-top: 1px dashed var(--line); }
.checks .mark { font-weight: 700; }
.checks .pass .mark { color: var(--pass); }
.checks .fail .mark, .checks .fail .result { color: var(--fail); }
.checks .name { overflow-wrap: anywhere; }
.checks .result { grid-column: 2; color: var(--muted); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.note { color: var(--muted); font-size: 13px; margin: 10px 0 0; }
.note.fail { color: var(--fail); }
.key { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 14px; color: var(--muted); }
.key img { width: 220px; }
.keys .takes { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.keys .note { margin: 0; }
"""


def record(title: str, checks: str, render: Render) -> dict:
    """What a render knows about its keys and moves. The ledger totals and the tape's size are read at write time."""
    return {
        "title": title,
        "checks": checks,
        "keys": [{**_shot_record(filmed, render.tape), "scene": filmed.shot.scene,
                  "key": f"keys/{filmed.shot.scene}.png", "items": _items(filmed.kept.checks)} for filmed in render.keys],
        "moves": [{**_shot_record(filmed, render.tape), "move": filmed.shot.move, "start": filmed.shot.start,
                   "land": filmed.shot.land, "label": filmed.shot.label} for filmed in render.moves],
    }


def rescored(record: dict, checks: str, scored: dict[str, KeyChecks]) -> dict:
    """The same record with every key's items replaced by what another eye read on its key image."""
    return {**record, "checks": checks,
            "keys": [{**key, "items": _items(scored[key["scene"]])} for key in record["keys"]]}


def read(tape: Path) -> dict:
    return json.loads((tape / "dailies.json").read_text())


def write(tape: Path, record: dict) -> None:
    played = [tape / "tape.json", *(tape / "keys").iterdir(), *(tape / "moves").iterdir()]
    record = {**record, "ledger": ledger.totals(ledger.read(tape)),
              "tape": {"bytes": sum(path.stat().st_size for path in played if path.is_file())}}
    publish(tape / "dailies.json", lambda partial: partial.write_text(json.dumps(record, indent=2) + "\n"))
    publish(tape / "dailies.html", lambda partial: partial.write_text(page(record)))


def page(record: dict) -> str:
    shots = [*record["keys"], *record["moves"]]
    rendered = sum(any(not take["cached"] for take in shot["takes"]) for shot in shots)
    failing = sum(_failing(_kept(shot)) for shot in shots)
    summary = f"{len(shots)} shots, {rendered} rendered this run, {len(shots) - rendered} from cache"
    if failing:
        summary += f", {failing} kept take{'s' if failing > 1 else ''} still failing"
    totals = record["ledger"]
    summary += (f". Ledger: {totals['gpu_seconds']} GPU seconds, {totals['pod_hours']} pod hours, ${totals['usd']:.2f}. "
                f"Tape: {record['tape']['bytes'] / 1e6:.1f} MB.")
    cards = "\n".join(_shot(number, shot) for number, shot in enumerate(shots, 1))
    title = escape(record["title"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} dailies</title>
<style>{STYLE}</style>
</head>
<body>
<header>
<h1>{title} dailies</h1>
<p class="summary">{summary}</p>
</header>
<main>
{_keys(record)}
{cards}
</main>
</body>
</html>
"""


def _shot_record(filmed: Filmed, tape: Path) -> dict:
    shot = filmed.shot
    return {
        "title": shot.title,
        "mode": shot.mode.value,
        "prompt": shot.prompt,
        "takes": [{"seed": take.seed, "clip": take.path.relative_to(tape).as_posix(), "cached": take.cached,
                   "kept": take is filmed.kept, "seconds": take.seconds, "gpu": take.gpu, "usd": take.usd,
                   **({"start": take.checks.start, "end": take.checks.end} if isinstance(shot, Move) else {}),
                   "items": _items(take.checks)} for take in filmed.takes],
    }


def _items(checks: Checks) -> list[dict]:
    return [asdict(item) for item in checks.items()]


def _kept(shot: dict) -> dict:
    return next(take for take in shot["takes"] if take["kept"])


def _failing(checked: dict) -> bool:
    return not all(item["passed"] for item in checked["items"])


def _checks(items: list[dict]) -> str:
    return "".join(
        f'<li class="{"pass" if item["passed"] else "fail"}"><span class="mark">{"✓" if item["passed"] else "✗"}</span>'
        f'<span class="name">{escape(item["name"])}</span><span class="result">{escape(item["result"])}</span></li>'
        for item in items)


def _keys(record: dict) -> str:
    checks = escape(record["checks"])
    keys = record["keys"]
    failing = sum(_failing(key) for key in keys)
    note = f"{len(keys)} keys checked by {checks}" + (f", {failing} failing" if failing else ", all passing")
    cards = "\n".join(_key(key, checks) for key in keys)
    return f"""<section class="shot keys" id="keys">
<div class="head"><h2>Keys</h2><span class="note">{note}</span></div>
<div class="takes">
{cards}
</div>
</section>"""


def _key(key: dict, checks: str) -> str:
    kept = _kept(key)
    badge = ' <span class="badge failing">fails checks</span>' if _failing(key) else ""
    return (f'<figure class="take"><img src="{escape(key["key"])}" alt="Key for {escape(key["scene"])}">'
            f'<figcaption><strong>{escape(key["scene"])}</strong><span class="badge">{checks}</span>{badge}</figcaption>'
            f'<ul class="checks">{_checks(key["items"])}</ul>'
            f'<p class="note">The last frame of take {kept["seed"]}, {_time(key)}.</p></figure>')


def _time(shot: dict) -> str:
    kept = _kept(shot)
    known = [take["seconds"] for take in shot["takes"] if take["seconds"] is not None]
    seconds = f'rendered in {kept["seconds"]:.1f} s' if kept["seconds"] is not None else "render time unknown"
    gpu = f' on {escape(kept["gpu"])}' if kept["gpu"] else ""
    return f'{seconds}, all {len(shot["takes"])} takes in {sum(known):.1f} s{gpu}'


def _shot(number: int, shot: dict) -> str:
    kept = _kept(shot)
    count = sum(not take["cached"] for take in shot["takes"])
    status = (f'<span class="badge rendered">rendered {count} take{"s" if count > 1 else ""} this run</span>'
              if count else '<span class="badge">from cache</span>')
    if _failing(kept):
        status += ' <span class="badge failing">kept take fails checks</span>'
    takes = "\n".join(_take(take) for take in shot["takes"])
    notes = []
    if "move" in shot:
        seams = f'Seams: leaves {escape(shot["start"])} by {kept["start"]:.3f}, enters {escape(shot["land"])} by {kept["end"]:.3f}.'
        passed = all(item["passed"] for item in kept["items"])
        notes.append(f'<p class="note{"" if passed else " fail"}">{seams}</p>')
    notes.append(f'<p class="note">The kept take {_time(shot)}.</p>')
    if "key" in shot:
        notes.append(f'<div class="key"><img src="{escape(shot["key"])}" alt="Key for {escape(shot["scene"])}" loading="lazy">'
                     f'<span>Gave <strong>{escape(shot["scene"])}</strong> its key: the last frame of take {kept["seed"]}.</span></div>')
    return f"""<section class="shot" id="shot-{number}">
<div class="head"><h2>{number}. {escape(shot["title"])} ({shot["mode"]})</h2><div>{status}</div></div>
<details><summary>Prompt</summary><p>{escape(shot["prompt"])}</p></details>
<div class="takes">
{takes}
</div>
{"".join(notes)}
</section>"""


def _take(take: dict) -> str:
    badge = ' <span class="badge kept">kept</span>' if take["kept"] else ""
    seconds = f'<span class="badge">{take["seconds"]:.1f} s</span>' if take["seconds"] is not None else ""
    return (f'<figure class="take{" kept" if take["kept"] else ""}">'
            f'<video src="{escape(take["clip"])}" autoplay loop muted playsinline preload="metadata"></video>'
            f'<figcaption><strong>Take {take["seed"]}</strong>{badge}'
            f'<span class="badge">{"cached" if take["cached"] else "rendered"}</span>{seconds}</figcaption>'
            f'<ul class="checks">{_checks(take["items"])}</ul></figure>')
