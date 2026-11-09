from __future__ import annotations

import json
from dataclasses import asdict
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from videotape import ledger
from videotape.checks import MAX_DIFFERENCE, Checks
from videotape.publish import publish
from videotape.shots import Mode

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
video, img { display: block; width: 100%; height: auto; aspect-ratio: 1280 / 704; border-radius: 6px; background: #000; }
figcaption { display: flex; align-items: center; gap: 8px; margin: 8px 0 4px; }
.checks { list-style: none; margin: 0; padding: 0; font-size: 13px; }
.checks li { display: grid; grid-template-columns: 1.2em 1fr; column-gap: 4px; padding: 2px 0;
  border-top: 1px dashed var(--line); }
.checks .mark { font-weight: 700; }
.checks .pass .mark { color: var(--pass); }
.checks .fail .mark, .checks .fail .result { color: var(--fail); }
.checks .name { overflow-wrap: anywhere; }
.checks .result { grid-column: 2; color: var(--muted); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.key { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 14px; color: var(--muted); }
.key img { width: 220px; }
.keys .takes { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.keys .note { color: var(--muted); font-size: 13px; }
"""


def record(title: str, render: Render) -> dict:
    return {"title": title, "shots": [_shot_record(filmed, render.tape) for filmed in render.shots]}


def keys(checks: str, scored: list[tuple[str, str, Checks]], shots: list[dict]) -> dict:
    return {"checks": checks, "scenes": [{"scene": scene, "key": key, "items": _items(found), "seams": _seams(scene, shots),
                                          "time": _time(scene, shots)} for scene, key, found in scored]}


def read(tape: Path) -> dict:
    return json.loads((tape / "dailies.json").read_text())


def write(tape: Path, record: dict) -> None:
    record = {**record, "ledger": ledger.totals(ledger.read(tape))}
    publish(tape / "dailies.json", lambda partial: partial.write_text(json.dumps(record, indent=2) + "\n"))
    publish(tape / "dailies.html", lambda partial: partial.write_text(page(record)))


def page(record: dict) -> str:
    shots = record["shots"]
    rendered = sum(any(not take["cached"] for take in shot["takes"]) for shot in shots)
    failing = sum(_failing(_kept(shot)) for shot in shots)
    summary = f"{len(shots)} shots, {rendered} rendered this run, {len(shots) - rendered} from cache"
    if failing:
        summary += f", {failing} kept take{'s' if failing > 1 else ''} still failing"
    totals = record["ledger"]
    summary += f". Ledger: {totals['gpu_seconds']} GPU seconds, {totals['pod_hours']} pod hours, ${totals['usd']:.2f}."
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
{_keys(record["keys"])}
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
        "move": shot.move,
        "prompt": shot.prompt,
        "scene": shot.start,
        "land": shot.land,
        "key": filmed.key.relative_to(tape).as_posix() if filmed.key else None,
        "takes": [{"seed": take.seed, "clip": take.path.relative_to(tape).as_posix(), "cached": take.cached,
                   "kept": take is filmed.kept, "seconds": take.seconds, "gpu": take.gpu,
                   "start": take.checks.start, "end": take.checks.end, "items": _items(take.checks)} for take in filmed.takes],
    }


def _items(checks: Checks) -> list[dict]:
    return [asdict(item) for item in checks.items()]


def _kept(shot: dict) -> dict:
    return next(take for take in shot["takes"] if take["kept"])


def _failing(checked: dict) -> bool:
    return not all(item["passed"] for item in checked["items"])


def _seams(scene: str, shots: list[dict]) -> list[dict]:
    """Where the player cuts between a key and a clip: a move's first frame against the key it leaves, and a
    first-and-last-frame move's last frame against the key it lands on."""
    seams = []
    for shot in shots:
        kept = _kept(shot)
        if shot["scene"] == scene:
            seams.append(_seam(shot["move"], "leaves", kept["start"]))
        if shot["land"] == scene and shot["mode"] == Mode.FIRST_AND_LAST_FRAME.value:
            seams.append(_seam(shot["move"], "enters", kept["end"]))
    return seams


def _seam(move: str, edge: str, difference: float) -> dict:
    return {"move": move, "edge": edge, "difference": difference, "passed": difference <= MAX_DIFFERENCE}


def _time(scene: str, shots: list[dict]) -> dict:
    shot = next(shot for shot in shots if shot["land"] == scene and shot["key"])
    known = [take["seconds"] for take in shot["takes"] if take["seconds"] is not None]
    return {"move": shot["move"], "kept": _kept(shot)["seconds"], "total": round(sum(known), 3), "gpu": _kept(shot)["gpu"]}


def _checks(items: list[dict]) -> str:
    return "".join(
        f'<li class="{"pass" if item["passed"] else "fail"}"><span class="mark">{"✓" if item["passed"] else "✗"}</span>'
        f'<span class="name">{escape(item["name"])}</span><span class="result">{escape(item["result"])}</span></li>'
        for item in items)


def _keys(keys: dict) -> str:
    checks = escape(keys["checks"])
    failing = sum(_failing(scene) for scene in keys["scenes"])
    note = f"{len(keys['scenes'])} keys checked by {checks}" + (f", {failing} failing" if failing else ", all passing")
    cards = "\n".join(_key(scene, checks) for scene in keys["scenes"])
    return f"""<section class="shot keys" id="keys">
<div class="head"><h2>Keys</h2><span class="note">{note}</span></div>
<div class="takes">
{cards}
</div>
</section>"""


def _key(scene: dict, checks: str) -> str:
    failing = _failing(scene) or not all(seam["passed"] for seam in scene["seams"])
    badge = ' <span class="badge failing">fails checks</span>' if failing else ""
    seams = [{"name": f'seam: {seam["edge"]} by {seam["move"]}', "result": f'difference {seam["difference"]:.3f}',
              "passed": seam["passed"]} for seam in scene["seams"]]
    time = scene["time"]
    kept = f'{time["kept"]:.1f} s' if time["kept"] is not None else "unknown"
    gpu = f' on {escape(time["gpu"])}' if time["gpu"] else ""
    rendered = f'Rendered by {escape(time["move"])}: the kept take in {kept}, all its takes in {time["total"]:.1f} s{gpu}.'
    return (f'<figure class="take"><img src="{escape(scene["key"])}" alt="Key for {escape(scene["scene"])}">'
            f'<figcaption><strong>{escape(scene["scene"])}</strong><span class="badge">{checks}</span>{badge}</figcaption>'
            f'<ul class="checks">{_checks(scene["items"])}{_checks(seams)}</ul><p class="note">{rendered}</p></figure>')


def _shot(number: int, shot: dict) -> str:
    kept = _kept(shot)
    count = sum(not take["cached"] for take in shot["takes"])
    status = (f'<span class="badge rendered">rendered {count} take{"s" if count > 1 else ""} this run</span>'
              if count else '<span class="badge">from cache</span>')
    if _failing(kept):
        status += ' <span class="badge failing">kept take fails checks</span>'
    takes = "\n".join(_take(take) for take in shot["takes"])
    key = ""
    if shot["key"]:
        key = (f'<div class="key"><img src="{escape(shot["key"])}" alt="Key for {escape(shot["land"])}" loading="lazy">'
               f'<span>Gave <strong>{escape(shot["land"])}</strong> its key: the last frame of take {kept["seed"]}.</span></div>')
    return f"""<section class="shot" id="shot-{number}">
<div class="head"><h2>{number}. {escape(shot["title"])} ({shot["mode"]})</h2><div>{status}</div></div>
<details><summary>Prompt</summary><p>{escape(shot["prompt"])}</p></details>
<div class="takes">
{takes}
</div>
{key}
</section>"""


def _take(take: dict) -> str:
    badge = ' <span class="badge kept">kept</span>' if take["kept"] else ""
    seconds = f'<span class="badge">{take["seconds"]:.1f} s</span>' if take["seconds"] is not None else ""
    return (f'<figure class="take{" kept" if take["kept"] else ""}">'
            f'<video src="{escape(take["clip"])}" autoplay loop muted playsinline preload="metadata"></video>'
            f'<figcaption><strong>Take {take["seed"]}</strong>{badge}'
            f'<span class="badge">{"cached" if take["cached"] else "rendered"}</span>{seconds}</figcaption>'
            f'<ul class="checks">{_checks(take["items"])}</ul></figure>')
