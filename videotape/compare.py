"""Two tapes of one screenplay, shot by shot, in one page: each shot's kept take from both, what the checks found on
each key, and how each move gets from one key to the other."""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from pathlib import Path

from videotape import dailies, frames, ledger
from videotape.publish import publish

STILLS = (0.0, 0.25, 0.5, 0.75, 1.0)
STILL_WIDTH = 480
STYLE = dailies.STYLE + """
.tapes { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; margin-top: 16px; }
.tapes .take h2 { margin-bottom: 6px; }
.tapes a { color: inherit; }
.facts { margin: 0; padding-left: 18px; font-size: 14px; }
.facts li { padding: 1px 0; }
.sides { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; margin-top: 14px; }
.side { margin: 0; border: 1px solid var(--line); border-radius: 10px; padding: 10px; min-width: 0; }
.side figcaption { margin-top: 0; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.pair figure { margin: 0; }
.pair figcaption, .strip figcaption { justify-content: center; margin: 2px 0 0; font-size: 12px; color: var(--muted); }
.strip { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; margin-top: 8px; }
.strip figure { margin: 0; }
.missing { color: var(--fail); }
"""


class CompareError(RuntimeError):
    pass


@dataclass(frozen=True)
class Tape:
    """A rendered tape as its dailies record, its manifest and its ledger lines describe it."""

    path: Path
    record: dict
    manifest: dict
    lines: list[dict]

    @property
    def model(self) -> str:
        return ", ".join(sorted({line["model"] for line in self.lines if line["kind"] == "take"})) or "unknown model"

    @property
    def usd_per_hour(self) -> float | None:
        """What the tape's pods cost an hour, averaged over their seconds, or None when it rented no pod."""
        pods = [line for line in self.lines if line["kind"] == "pod"]
        seconds = sum(pod["seconds"] for pod in pods)
        return sum(pod["usd"] for pod in pods) * 3600 / seconds if seconds else None

    def usd(self, take: dict) -> float:
        """A take paid per call costs what it was billed. A take on a rented pod costs its GPU seconds at the pod's
        price, without the pod's setup. A take on this machine costs nothing."""
        if take.get("usd") is not None:
            return take["usd"]
        return (take["seconds"] or 0.0) * self.usd_per_hour / 3600 if self.usd_per_hour else 0.0

    @property
    def basis(self) -> str:
        if any(take.get("usd") is not None for shot in _shots(self.record) for take in shot["takes"]):
            return "as billed per call"
        if self.usd_per_hour:
            return f"GPU time at the pod's ${self.usd_per_hour:.2f}/h, setup excluded"
        return "rendered on this machine"


def read(path: Path) -> Tape:
    for name in ("tape.json", "dailies.json"):
        if not (path / name).is_file():
            raise CompareError(f"no {name} in {path}; render a screenplay into it first")
    record = dailies.read(path)
    if not isinstance(record.get("keys"), list):
        raise CompareError(f"{path / 'dailies.json'} is from an older render; render the screenplay again to write it")
    return Tape(path, record, json.loads((path / "tape.json").read_text()), ledger.read(path))


def compare(tapes: tuple[Tape, Tape]) -> Path:
    """Write compare.html, and the stills it shows, in the folder the two tapes share."""
    a, b = (tape.path for tape in tapes)
    folder = Path(os.path.commonpath([os.path.abspath(a), os.path.abspath(b)]))
    if folder == Path(folder.anchor):
        raise CompareError(f"{a} and {b} share no folder to write compare.html in")
    stills = folder / "compare-frames"
    for side, tape in zip("ab", tapes):
        (stills / side).mkdir(parents=True, exist_ok=True)
        for move in tape.record["moves"]:
            frames.stills(tape.path / _kept(move)["clip"], STILLS, STILL_WIDTH, _stills(stills / side, move))
    motions = {letter: {move["title"]: frames.motion(tape.path / _kept(move)["clip"]) for move in tape.record["moves"]}
               for letter, tape in zip("AB", tapes)}
    out = folder / "compare.html"
    publish(out, lambda partial: partial.write_text(page(tapes, motions, folder)))
    return out


def page(tapes: tuple[Tape, Tape], motions: dict[str, dict[str, float]], folder: Path) -> str:
    """motions holds each move's frame-to-frame difference by title, for tape A and tape B."""
    title = escape(tapes[0].record["title"])
    keys = _matched([tape.record["keys"] for tape in tapes])
    moves = _matched([tape.record["moves"] for tape in tapes])
    cards = [_card(number, pair, tapes, lambda letter, tape, key: _key(letter, tape, key, folder))
             for number, pair in enumerate(keys, 1)]
    cards += [_card(number, pair, tapes,
                    lambda letter, tape, move: _move(letter, tape, move, motions[letter][move["title"]], folder))
              for number, pair in enumerate(moves, len(keys) + 1)]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} compare</title>
<style>{STYLE}</style>
</head>
<body>
<header>
<h1>{title} compare</h1>
<p class="summary">The same {len(keys) + len(moves)} shots from two tapes, matched by title. Each key shows every button
found or not found and every line and label as read, with its character error rate. Each move shows its seams and five
frames from its start to its end.</p>
<div class="tapes">
{"".join(_totals(side, tape, folder) for side, tape in zip("AB", tapes))}
</div>
</header>
<main>
{chr(10).join(cards)}
</main>
</body>
</html>
"""


def summary(side: str, tape: Tape) -> str:
    """The line the CLI prints for one tape."""
    found, buttons = _passed(tape.record["keys"], "button")
    size = tape.manifest["size"]
    return (f"{side} {tape.path}  {tape.model}  {size['width']}x{size['height']} at {tape.manifest['fps']} fps  "
            f"{ledger.totals(tape.lines)['takes']} takes  ${ledger.totals(tape.lines)['usd']:.2f}  "
            f"buttons found {found} of {buttons}")


def _shots(record: dict) -> list[dict]:
    return [*record["keys"], *record["moves"]]


def _kept(shot: dict) -> dict:
    return next(take for take in shot["takes"] if take["kept"])


def _matched(sides: list[list[dict]]) -> list[tuple[dict | None, dict | None]]:
    """Every title in either tape, in the first tape's order and then the second's, with each tape's shot or None."""
    titles = list(dict.fromkeys(shot["title"] for shots in sides for shot in shots))
    by_title = [{shot["title"]: shot for shot in shots} for shots in sides]
    return [(by_title[0].get(title), by_title[1].get(title)) for title in titles]


def _passed(keys: list[dict], kind: str) -> tuple[int, int]:
    """How many of the keys' button or text checks passed, out of how many, from items named like 'button "Sign up"'."""
    items = [item for key in keys for item in key["items"] if item["name"].startswith(f"{kind} ")]
    return sum(item["passed"] for item in items), len(items)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _stills(folder: Path, move: dict) -> list[Path]:
    return [folder / f"{move['move']}-{round(fraction * 100):03d}.png" for fraction in STILLS]


def _href(path: Path, folder: Path) -> str:
    return escape(Path(os.path.relpath(path, folder)).as_posix())


def _totals(side: str, tape: Tape, folder: Path) -> str:
    totals = ledger.totals(tape.lines)
    size = tape.manifest["size"]
    found, buttons = _passed(tape.record["keys"], "button")
    exact, texts = _passed(tape.record["keys"], "text")
    takes = sum(tape.usd(take) for shot in _shots(tape.record) for take in shot["takes"])
    pods = f", {_plural(totals['pods'], 'pod')} for {totals['pod_hours']} h with setup" if totals["pods"] else ""
    return f"""<section class="take">
<h2>{side}. <a href="{_href(tape.path / "dailies.html", folder)}">{escape(tape.path.name)}</a></h2>
<ul class="facts">
<li>{escape(tape.model)}, checked by {escape(tape.record["checks"])}</li>
<li>{size["width"]}x{size["height"]} at {tape.manifest["fps"]} fps</li>
<li>{totals["takes"]} takes filmed in {totals["gpu_seconds"]} s{pods}</li>
<li>${totals["usd"]:.2f} in the ledger; the takes cost ${takes:.2f}, {escape(tape.basis)}</li>
<li>{found} of {buttons} buttons found, {exact} of {texts} lines and labels read exactly</li>
</ul>
</section>"""


def _head(number: int, pair: tuple[dict | None, dict | None]) -> str:
    shot = pair[0] or pair[1]
    prompts = {side["prompt"] for side in pair if side}
    differ = ' <span class="badge failing">prompts differ</span>' if len(prompts) > 1 else ""
    shown = "".join(f"<p>{escape(prompt)}</p>" for prompt in sorted(prompts))
    return (f'<div class="head"><h2>{number}. {escape(shot["title"])} ({shot["mode"]})</h2>{differ}</div>'
            f"<details><summary>Prompt</summary>{shown}</details>")


def _caption(letter: str, tape: Tape, shot: dict, items: list[dict]) -> str:
    failing = "" if all(item["passed"] for item in items) else ' <span class="badge failing">fails checks</span>'
    return (f'<figcaption><strong>{letter}. {escape(tape.path.name)}</strong><span class="badge">{escape(tape.model)}</span>'
            f'<span class="badge kept">kept take {_kept(shot)["seed"]}</span>{failing}</figcaption>')


def _cost(tape: Tape, shot: dict) -> str:
    kept = _kept(shot)
    known = [take["seconds"] for take in shot["takes"] if take["seconds"] is not None]
    time = f'Kept take rendered in {kept["seconds"]:.1f} s' if kept["seconds"] is not None else "Render time unknown"
    usd = sum(tape.usd(take) for take in shot["takes"])
    return (f'<p class="note">{time}. {_plural(len(shot["takes"]), "take")} in {sum(known):.1f} s for ${usd:.2f}, '
            f'{escape(tape.basis)}.</p>')


def _card(number: int, pair: tuple[dict | None, dict | None], tapes: tuple[Tape, Tape],
          side: Callable[[str, Tape, dict], str]) -> str:
    """One shot's card, with side(letter, tape, shot) drawn for each tape that has the shot."""
    sides = [side(letter, tape, shot) if shot else
             f'<figure class="side"><figcaption><strong>{letter}. {escape(tape.path.name)}</strong></figcaption>'
             f'<p class="note missing">This shot is not in this tape.</p></figure>'
             for letter, tape, shot in zip("AB", tapes, pair)]
    return f"""<section class="shot" id="shot-{number}">
{_head(number, pair)}
<div class="sides">
{chr(10).join(sides)}
</div>
</section>"""


def _key(letter: str, tape: Tape, key: dict, folder: Path) -> str:
    found, buttons = _passed([key], "button")
    tally = f"{found} of {_plural(buttons, 'button')} found." if buttons else "No buttons to find."
    return (f'<figure class="side">{_caption(letter, tape, key, key["items"])}'
            f'<div class="pair"><figure><video src="{_href(tape.path / _kept(key)["clip"], folder)}" autoplay loop muted'
            f' playsinline preload="metadata"></video><figcaption>kept take</figcaption></figure>'
            f'<figure><img src="{_href(tape.path / key["key"], folder)}" alt="Key for {escape(key["scene"])} in {letter}"'
            f' loading="lazy"><figcaption>key, its last frame</figcaption></figure></div>'
            f'<p class="note{"" if found == buttons else " fail"}">{tally}</p>'
            f'<ul class="checks">{dailies.checklist(key["items"])}</ul>{_cost(tape, key)}</figure>')


def _move(letter: str, tape: Tape, move: dict, motion: float, folder: Path) -> str:
    kept = _kept(move)
    seams = all(item["passed"] for item in kept["items"])
    stills = _stills(folder / "compare-frames" / letter.lower(), move)
    strip = "".join(f'<figure><img src="{_href(still, folder)}" alt="{round(fraction * 100)}% of the move in {letter}"'
                    f' loading="lazy"><figcaption>{round(fraction * 100)}%</figcaption></figure>'
                    for fraction, still in zip(STILLS, stills))
    return (f'<figure class="side">{_caption(letter, tape, move, kept["items"])}'
            f'<video src="{_href(tape.path / kept["clip"], folder)}" autoplay loop muted playsinline preload="metadata">'
            f'</video><div class="strip">{strip}</div>'
            f'<p class="note{"" if seams else " fail"}">Seams: leaves {escape(move["start"])} by {kept["start"]:.3f}, '
            f'enters {escape(move["land"])} by {kept["end"]:.3f}.</p>'
            f'<p class="note">Each frame differs from the next by {motion:.4f} on average.</p>'
            f'{_cost(tape, move)}</figure>')
