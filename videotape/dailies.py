from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from videotape.render import Filmed, Render, Take

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
.checks li { display: grid; grid-template-columns: 1.2em 1fr auto; gap: 4px; padding: 2px 0;
  border-top: 1px dashed var(--line); }
.checks .mark { font-weight: 700; }
.checks .pass .mark { color: var(--pass); }
.checks .fail .mark, .checks .fail .result { color: var(--fail); }
.checks .name { overflow-wrap: anywhere; }
.checks .result { color: var(--muted); font-variant-numeric: tabular-nums; text-align: right; }
.key { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 14px; color: var(--muted); }
.key img { width: 220px; }
"""


def page(title: str, render: Render) -> str:
    rendered = sum(bool(filmed.rendered) for filmed in render.shots)
    failing = sum(bool(filmed.kept.checks.failures) for filmed in render.shots)
    summary = f"{len(render.shots)} shots, {rendered} rendered this run, {len(render.shots) - rendered} from cache"
    if failing:
        summary += f", {failing} kept take{'s' if failing > 1 else ''} still failing"
    shots = "\n".join(_shot(number, filmed, render) for number, filmed in enumerate(render.shots, 1))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} dailies</title>
<style>{STYLE}</style>
</head>
<body>
<header>
<h1>{escape(title)} dailies</h1>
<p class="summary">{summary}</p>
</header>
<main>
{shots}
</main>
</body>
</html>
"""


def _shot(number: int, filmed: Filmed, render: Render) -> str:
    shot = filmed.shot
    status = (f'<span class="badge rendered">rendered {filmed.rendered} take{"s" if filmed.rendered > 1 else ""} this run</span>'
              if filmed.rendered else '<span class="badge">from cache</span>')
    if filmed.kept.checks.failures:
        status += ' <span class="badge failing">kept take fails checks</span>'
    takes = "\n".join(_take(take, take is filmed.kept, render) for take in filmed.takes)
    key = ""
    if filmed.key:
        key = (f'<div class="key"><img src="{escape(filmed.key.relative_to(render.tape).as_posix())}" '
               f'alt="Key for {escape(shot.land)}" loading="lazy"><span>Gave <strong>{escape(shot.land)}</strong> '
               f'its key: the last frame of take {filmed.kept.seed}.</span></div>')
    return f"""<section class="shot" id="shot-{number}">
<div class="head"><h2>{number}. {escape(shot.title)} ({shot.mode.value})</h2><div>{status}</div></div>
<details><summary>Prompt</summary><p>{escape(shot.prompt)}</p></details>
<div class="takes">
{takes}
</div>
{key}
</section>"""


def _take(take: Take, kept: bool, render: Render) -> str:
    checks = "".join(
        f'<li class="{"pass" if item.passed else "fail"}"><span class="mark">{"✓" if item.passed else "✗"}</span>'
        f'<span class="name">{escape(item.name)}</span><span class="result">{escape(item.result)}</span></li>'
        for item in take.checks.items())
    badge = ' <span class="badge kept">kept</span>' if kept else ""
    source = escape(take.path.relative_to(render.tape).as_posix())
    return (f'<figure class="take{" kept" if kept else ""}">'
            f'<video src="{source}" autoplay loop muted playsinline preload="metadata"></video>'
            f'<figcaption><strong>Take {take.seed}</strong>{badge}'
            f'<span class="badge">{"cached" if take.cached else "rendered"}</span></figcaption>'
            f'<ul class="checks">{checks}</ul></figure>')
