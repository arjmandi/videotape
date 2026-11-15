"""The dailies: a tape's record of what a render knew about its keys and moves, dailies.json, and the page a person
reviews it on, dailies.html. The record is also where accepts, retake seeds and corrupt seeds live, so a render reads
it first and carries them over when it writes it again."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from videotape import errors, frames
from videotape.checks import Checks, Failure
from videotape.frames import Box, Frame
from videotape.plan import Key, Move, Shot
from videotape.atomic import write_atomically
from videotape.story import FromStory, Story, line_of, text

if TYPE_CHECKING:
    from videotape.render import Filmed, Render

PAD = 24
"""Pixels of frame kept around a failure's box in its crop, so the person sees where it sits."""


@dataclass(frozen=True)
class Carried:
    """What a tape's record carries from one render to the next, each by the shot's title: the seeds a retake added,
    the seeds whose takes were corrupt, and the failures a person accepted."""

    retakes: dict[str, list[int]] = field(default_factory=dict)
    corrupt: dict[str, list[int]] = field(default_factory=dict)
    accepted: list[dict] = field(default_factory=list)


def carried(tape: Path) -> Carried:
    if not (tape / "dailies.json").is_file():
        return Carried()
    held = read(tape)
    return Carried(dict(held.get("retakes", {})), dict(held.get("corrupt", {})), list(held.get("accepted", [])))


def named(shot: Shot) -> str:
    """How retake and accept name a shot: a state, or a move as its two states."""
    return shot.state.name if isinstance(shot, Key) else f"{shot.start.name} -> {shot.land.name}"


STYLE = """
:root { color-scheme: light dark; --bg: #f5f2ec; --card: #fffdf9; --text: #22262a; --muted: #646d75;
  --line: #e4ded3; --pass: #1d7a4a; --fail: #b42318; --kept: #c66a00; --kept-soft: #fff1dc; --fail-soft: #fde8e6; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #131619; --card: #1b1f23; --text: #e9e6e0; --muted: #98a1a9; --line: #2c3238;
    --pass: #63d297; --fail: #ff8f85; --kept: #ffb457; --kept-soft: #3a2a14; --fail-soft: #3a1a18; }
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
h3 { font-size: 15px; margin: 16px 0 8px; }
.badge { font-size: 12px; font-weight: 600; border-radius: 999px; padding: 2px 10px; border: 1px solid var(--line);
  color: var(--muted); white-space: nowrap; }
.badge.rendered { color: var(--pass); border-color: currentColor; }
.badge.kept { color: var(--kept); border-color: currentColor; background: var(--kept-soft); }
.badge.failing { color: var(--fail); border-color: currentColor; }
.badge.accepted { color: var(--pass); border-color: currentColor; }
details { margin-top: 8px; color: var(--muted); font-size: 13px; }
summary { cursor: pointer; }
.takes { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; margin-top: 14px; }
.take { margin: 0; border: 1px solid var(--line); border-radius: 10px; padding: 10px; }
.take.kept { border: 2px solid var(--kept); padding: 9px; }
video, img { display: block; width: 100%; height: auto; border-radius: 6px; background: #000; }
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
.failures { border-color: var(--fail); }
.failure { display: grid; grid-template-columns: minmax(200px, 320px) 1fr; gap: 16px; padding: 12px 0;
  border-top: 1px solid var(--line); }
.failure.accepted { opacity: 0.75; }
.failure img { aspect-ratio: auto; border: 1px solid var(--line); }
.failure .about { margin: 0 0 4px; }
.failure .evidence { color: var(--fail); font-size: 13px; margin: 0 0 8px; overflow-wrap: anywhere; }
.failure .reason { color: var(--pass); font-size: 13px; margin: 0 0 8px; }
.failure .again { color: var(--kept); font-size: 13px; margin: 0 0 8px; }
.next { margin: 0; padding-left: 20px; font-size: 13px; }
.next li { margin: 2px 0; overflow-wrap: anywhere; }
code { background: var(--kept-soft); padding: 1px 5px; border-radius: 4px; font-size: 12px; }
@media (max-width: 640px) { .failure { grid-template-columns: 1fr; } }
"""

# A browser refuses to hold more than a few dozen videos at once, and an app has hundreds of takes, so a take loads
# and plays only while it is near the window.
SCRIPT = """
const near = new IntersectionObserver(entries => {
  for (const {target, isIntersecting} of entries) {
    if (isIntersecting) { target.src = target.dataset.src; target.play().catch(() => {}); }
    else if (target.hasAttribute("src")) { target.removeAttribute("src"); target.load(); }
  }
}, {rootMargin: "400px"});
document.querySelectorAll("video").forEach(video => near.observe(video));
"""


def record(title: str, checks: str, render: Render, story: Story, tape_name: str, carry: Carried, takes: int,
           complete: bool = True) -> dict:
    """What a render knows about its keys and moves, with every failure of a kept take and its next steps, and what
    carries on to the next render: the accepts, the retake seeds, the corrupt seeds, and the limit on takes. complete
    is false for a render that stopped short of its last shot. The ledger totals and the tape's size are read at
    write time."""
    out = None if tape_name == f"tapes/{story.name}" else tape_name
    shots = render.shots
    return {
        "title": title,
        "checks": checks,
        "story": story.name,
        "out": out,
        "takes": takes,
        "complete": complete,
        "keys": [{**_shot_record(filmed, render.tape), "state": filmed.shot.state.name, "key": filmed.shot.image,
                  "items": _items(filmed.kept.checks)} for filmed in render.keys],
        "moves": [{**_shot_record(filmed, render.tape), "move": filmed.shot.clip, "start": filmed.shot.start.name,
                   "land": filmed.shot.land.name, "label": filmed.shot.label} for filmed in render.moves],
        "failures": [_failure(failure, filmed, story, out, carry, render.tape)
                     for filmed in shots for failure in filmed.failures],
        "yield": {"first_take": sum(filmed.takes[0].checks.passed for filmed in shots), "shots": len(shots)},
        "retakes": carry.retakes,
        "corrupt": carry.corrupt,
        "accepted": carry.accepted,
    }


def read(tape: Path) -> dict:
    return json.loads((tape / "dailies.json").read_text())


def recorded(tape: Path, render: str) -> dict:
    """The tape's record: VT405 when nothing rendered into the tape. render is the command that renders it."""
    if not (tape / "dailies.json").is_file():
        raise errors.ScreenplayError("VT405", errors.shown(tape), "has no dailies.json, which every render writes",
                                     f"render the story first, as in:\n{render}")
    return read(tape)


def write(tape: Path, record: dict, totals: dict) -> None:
    """Write the record and its page into the tape, with the ledger's totals for this tape, the size of what plays,
    the size of its frames, and a crop for each failure. The crops of failures the record no longer holds are
    deleted."""
    played = ["tape.json", "moves/opening.mp4", *(key["key"] for key in record["keys"]),
              *(move["move"] for move in record["moves"])]
    size = sum((tape / path).stat().st_size for path in played if (tape / path).is_file())
    pictures = [tape / key["key"] for key in record["keys"] if (tape / key["key"]).is_file()]
    shape = frames.shape(pictures[0]) if pictures else None
    failures = [{**failure, "crop": _crop(tape, number, failure)} for number, failure in enumerate(record["failures"], 1)]
    crops = {failure["crop"] for failure in failures}
    for png in (tape / "dailies").glob("*.png"):
        if png.relative_to(tape).as_posix() not in crops:
            png.unlink()
    record = {**record, "failures": failures, "ledger": totals, "tape": {"bytes": size},
              "frame": {"width": shape.width, "height": shape.height} if shape else None}
    write_atomically(tape / "dailies.json", lambda partial: partial.write_text(json.dumps(record, indent=2) + "\n"))
    write_atomically(tape / "dailies.html", lambda partial: partial.write_text(page(record)))


def verdict(accepts: list[dict], shot: str, code: str, clip: str) -> dict:
    """What a person said of a failure of this code on this take of the shot. An accept holds for the take it was
    given on, by its clip, since a take filmed again from a changed prompt or key image keeps its seed and gets new
    pixels. One given on another take, or before an accept named its take, is shown as accepted_before, and the
    failure fails again until a person looks at the new take."""
    accept = next((accept for accept in accepts if (accept["shot"], accept["code"]) == (shot, code)), None)
    if accept is None:
        return {"accepted": None, "accepted_before": None}
    said = {"reason": accept["reason"], "at": accept["at"]}
    if accept.get("clip") == clip:
        return {"accepted": said, "accepted_before": None}
    return {"accepted": None, "accepted_before": {**said, "seed": accept.get("seed")}}


def _shot_record(filmed: Filmed, tape: Path) -> dict:
    shot = filmed.shot
    return {
        "title": shot.title,
        "mode": shot.mode.value,
        "prompt": text(filmed.prompt),
        "takes": [{"seed": take.seed, "clip": take.path.relative_to(tape).as_posix(), "cached": take.cached,
                   "kept": take is filmed.kept, "seconds": take.seconds, "gpu": take.gpu, "usd": take.usd,
                   **({"start": take.checks.start, "end": take.checks.end} if isinstance(shot, Move) else {}),
                   "items": _items(take.checks)} for take in filmed.takes],
        "corrupt": list(filmed.corrupt),
    }


def _items(checks: Checks) -> list[dict]:
    return [asdict(item) for item in checks.items()]


def _failure(failure: Failure, filmed: Filmed, story: Story, out: str | None, carry: Carried, tape: Path) -> dict:
    """One failure of a kept take: its evidence, where to crop, and its next steps in order: retake, change the story
    line that drew it, change the screenplay, accept it."""
    shot, kept = filmed.shot, filmed.kept
    name, where = named(shot), f" --out {out}" if out else ""
    box = failure.box or _found_elsewhere(failure, filmed)
    frame = "first" if failure.code == "VT508" and failure.about == "start" else "last"
    return {
        **asdict(failure),
        "take": kept.seed,
        "clip": kept.path.relative_to(tape).as_posix(),
        "frame": frame,
        "crop_box": asdict(box) if box else None,
        "next": {
            "retake": f'videotape retake "{name}" --story {story.name}{where}',
            "story": _story_line(failure, filmed, story),
            "screenplay": _screenplay_line(shot),
            "accept": f'videotape accept "{name}" {failure.code} --story {story.name}{where} --reason "..."',
        },
        **verdict(carry.accepted, shot.title, failure.code, kept.path.relative_to(tape).as_posix()),
    }


def _found_elsewhere(failure: Failure, filmed: Filmed) -> Box | None:
    """Where another take of the shot found what this one did not."""
    for take in filmed.takes:
        for item in take.checks.items():
            if (item.code, item.about) == (failure.code, failure.about) and item.box:
                return item.box
    return None


def _element_type(failure: Failure, shot: Shot) -> str | None:
    """The type of the element the failure is about: the one holding the action, the line, or the move."""
    if isinstance(shot, Move):
        return shot.element
    for element in shot.shown:
        for line in element.lines:
            if failure.code == "VT501" and line.action and line.action.label == failure.about:
                return element.type
            if failure.code == "VT502" and line.words == failure.about:
                return element.type
    return None


def _story_line(failure: Failure, filmed: Filmed, story: Story) -> str:
    """The story line that drew what failed, named from the prompt's clause sources: the element type's appearance
    or move, else the scene's direction, else the look."""
    shot, kind = filmed.shot, _element_type(failure, filmed.shot)
    sources = [clause.source.part for clause in filmed.prompt if isinstance(clause.source, FromStory)]
    wanted = [f"moves.{kind}", "moves.default"] if isinstance(shot, Move) else \
        [f"elements.{kind}", f"scenes.{shot.state.scene.name}", "look"]
    part = next((part for part in wanted if part in sources), sources[0] if sources else "look")
    table, _, name = part.partition(".")
    line = line_of(story.path, table, name) if name else line_of(story.path, None, part)
    return f"{errors.shown(story.path)}{f' line {line}' if line else ''}, {part}"


def _screenplay_line(shot: Shot) -> str:
    scene = shot.state.scene if isinstance(shot, Key) else shot.start.scene
    return f"{errors.shown(scene.defined[0])} line {scene.defined[1]}"


def _crop(tape: Path, number: int, failure: dict) -> str:
    """A PNG of where the failure is: its box with some frame around it, or the whole frame."""
    folder = tape / "dailies"
    folder.mkdir(exist_ok=True)
    clip = tape / failure["clip"]
    frame = frames.first_frame(clip) if failure["frame"] == "first" else frames.last_frame(clip)
    if box := failure.get("crop_box"):
        frame = _cut(frame, Box(**box))
    out = folder / f"{number}.png"
    write_atomically(out, lambda partial: frames.write_png(frame, partial))
    return out.relative_to(tape).as_posix()


def _cut(frame: Frame, box: Box) -> Frame:
    x0, y0 = max(0, box.x - PAD), max(0, box.y - PAD)
    x1, y1 = min(frame.width, box.x + box.w + PAD), min(frame.height, box.y + box.h + PAD)
    rows = [frame.rgb[(y * frame.width + x0) * 3:(y * frame.width + x1) * 3] for y in range(y0, y1)]
    return Frame(x1 - x0, y1 - y0, b"".join(rows))


def _frame(frame: dict | None) -> str:
    """Room for each picture and clip at the tape's own shape before it loads, which then keeps its own."""
    return f"video, img {{ aspect-ratio: auto {frame['width']} / {frame['height']}; }}\n" if frame else ""


def page(record: dict) -> str:
    shots = [*record["keys"], *record["moves"]]
    rendered = sum(any(not take["cached"] for take in shot["takes"]) for shot in shots)
    failing = sum(_failing(_kept(shot)) for shot in shots)
    summary = f"{len(shots)} shots, {rendered} rendered this run, {len(shots) - rendered} from cache"
    if failing:
        summary += f", {failing} kept take{'s' if failing > 1 else ''} still failing"
    first = record["yield"]
    summary += f". First-take yield {first['first_take']} of {first['shots']}."
    totals = record["ledger"]
    summary += (f" Ledger: {totals['gpu_seconds']} GPU seconds, {totals['pod_hours']} pod hours, ${totals['usd']:.2f}. "
                f"Tape: {record['tape']['bytes'] / 1e6:.1f} MB.")
    cards = "\n".join(_shot(number, shot) for number, shot in enumerate(shots, 1))
    title = escape(record["title"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} dailies</title>
<style>{STYLE}{_frame(record["frame"])}</style>
</head>
<body>
<header>
<h1>{title} dailies</h1>
<p class="summary">{summary}</p>
</header>
<main>
{_failures(record)}
{_keys(record)}
{cards}
</main>
<script>{SCRIPT}</script>
</body>
</html>
"""


def _kept(shot: dict) -> dict:
    return next(take for take in shot["takes"] if take["kept"])


def _failing(checked: dict) -> bool:
    return not all(item["passed"] for item in checked["items"])


def checklist(items: list[dict]) -> str:
    return "".join(
        f'<li class="{"pass" if item["passed"] else "fail"}"><span class="mark">{"✓" if item["passed"] else "✗"}</span>'
        f'<span class="name">{item["code"]} {escape(item["about"])}</span><span class="result">{escape(item["result"])}</span></li>'
        for item in items)


def _failures(record: dict) -> str:
    """Every failure of a kept take, first on the page, grouped by code, the ones a person accepted last in each."""
    failures = record["failures"]
    if not failures:
        return ""
    groups = []
    for code in sorted({failure["code"] for failure in failures}):
        of_code = sorted((f for f in failures if f["code"] == code), key=lambda f: f["accepted"] is not None)
        groups.append(f"<h3>{code} {escape(errors.CODES[code].title)}</h3>\n" + "\n".join(map(_failure_card, of_code)))
    open_ = sum(failure["accepted"] is None for failure in failures)
    note = f"{len(failures)} failing, {open_} to act on, {len(failures) - open_} accepted"
    return f"""<section class="shot failures" id="failures">
<div class="head"><h2>Failures</h2><span class="note fail">{note}</span></div>
{"".join(groups)}
</section>"""


def _failure_card(failure: dict) -> str:
    accepted = failure["accepted"]
    steps = failure["next"]
    badge = ' <span class="badge accepted">accepted</span>' if accepted else ""
    reason = f'<p class="reason">Accepted: {escape(accepted["reason"])}</p>' if accepted else ""
    if before := failure.get("accepted_before"):
        if before["seed"] is None:
            on, now = "an earlier render", f'this is take {failure["take"]}'
        elif before["seed"] == failure["take"]:
            on, now = f'take {before["seed"]}', "the take was filmed again"
        else:
            on, now = f'take {before["seed"]}', f'this is take {failure["take"]}'
        reason = f'<p class="again">Accepted on {on}: {escape(before["reason"])}; {now}, so look again</p>'
    return f"""<div class="failure{" accepted" if accepted else ""}">
<img src="{escape(failure["crop"])}" alt="Where {escape(failure["about"])} should be on {escape(failure["shot"])}" loading="lazy">
<div>
<p class="about"><strong>{escape(failure["shot"])}</strong> take {failure["take"]}: {escape(failure["about"])}{badge}</p>
<p class="evidence">{escape(failure["evidence"])}</p>
{reason}
<ol class="next">
<li>Retake it: <code>{escape(steps["retake"])}</code></li>
<li>Change the story line that drew it: {escape(steps["story"])}</li>
<li>Change the screenplay: {escape(steps["screenplay"])}</li>
<li>Accept it with a reason: <code>{escape(steps["accept"])}</code></li>
</ol>
</div>
</div>"""


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
    return (f'<figure class="take"><img src="{escape(key["key"])}" alt="Key for {escape(key["state"])}" loading="lazy">'
            f'<figcaption><strong>{escape(key["state"])}</strong><span class="badge">{checks}</span>{badge}</figcaption>'
            f'<ul class="checks">{checklist(key["items"])}</ul>'
            f'<p class="note">The last frame of take {kept["seed"]}, {_time(key)}.</p></figure>')


def _time(shot: dict) -> str:
    kept = _kept(shot)
    known = [take["seconds"] for take in shot["takes"] if take["seconds"] is not None]
    seconds = f'rendered in {kept["seconds"]:.1f} s' if kept["seconds"] is not None else "render time unknown"
    gpu = f' on {escape(kept["gpu"])}' if kept["gpu"] else ""
    count = len(shot["takes"])
    return f'{seconds}, {"all " if count > 1 else ""}{count} take{"s" if count > 1 else ""} in {sum(known):.1f} s{gpu}'


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
    if shot.get("corrupt"):
        notes.append(f'<p class="note fail">Corrupt and skipped: seed{"s" if len(shot["corrupt"]) > 1 else ""} '
                     f'{", ".join(map(str, shot["corrupt"]))}.</p>')
    notes.append(f'<p class="note">The kept take {_time(shot)}.</p>')
    if "key" in shot:
        notes.append(f'<div class="key"><img src="{escape(shot["key"])}" alt="Key for {escape(shot["state"])}" loading="lazy">'
                     f'<span>Gave <strong>{escape(shot["state"])}</strong> its key: the last frame of take {kept["seed"]}.</span></div>')
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
            f'<video data-src="{escape(take["clip"])}" loop muted playsinline preload="none"></video>'
            f'<figcaption><strong>Take {take["seed"]}</strong>{badge}'
            f'<span class="badge">{"cached" if take["cached"] else "rendered"}</span>{seconds}</figcaption>'
            f'<ul class="checks">{checklist(take["items"])}</ul></figure>')
