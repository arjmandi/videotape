import argparse
import json
import sys
from collections import Counter
from difflib import get_close_matches
from pathlib import Path

from videotape import dailies, errors, ledger, project, story
from videotape.checks import ChecksError
from videotape.errors import CODES, ScreenplayError
from videotape.fal import FalError
from videotape.frames import FfmpegError
from videotape.made import made
from videotape.model import MODELS, Listing
from videotape.plan import Key, Plan, plan
from videotape.project import Project, ProjectError
from videotape.render import render, uncached
from videotape.standin import StandInError
from videotape.story import Story
from videotape.wan import WanError


def _planned(found: Project) -> Plan:
    return plan(found.load(), found.max_states)


def _listing(found: Project, named: str | None) -> Listing | None:
    """The model a command names, or else the project's, or none when neither names one."""
    name = named or found.model
    if name is not None and name not in MODELS:
        raise ProjectError(f'[tool.videotape] sets model = "{name}", and the models are {", ".join(sorted(MODELS))}')
    return MODELS[name] if name else None


def _told(found: Project, planned: Plan, name: str,
          listing: Listing | None) -> tuple[Story, tuple[ScreenplayError, ...]]:
    """The project's story of this name, checked against the plan and the model, with the warnings of that check."""
    told = story.named(found.root, name)
    return told, story.check(told, planned, listing.prompt_limit if listing else None)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def plan_app(args) -> int:
    found = project.find(Path.cwd())
    if args.model and not args.story:
        raise ProjectError("--model checks a story's prompts against that model, so pass --story with it")
    planned = _planned(found)
    warnings, in_story = planned.warnings, ""
    if args.story:
        told, more = _told(found, planned, args.story, _listing(found, args.model))
        warnings, in_story = (*warnings, *more), f" + {told.name} {told.version}"
    states, moves = len(planned.keys), len(planned.moves)
    per_scene = Counter(key.state.scene.name for key in planned.keys)
    out = Counter(move.start.scene.name for move in planned.moves)
    print(f"{' '.join(filter(None, (planned.title, found.version)))}{in_story}: {_count(len(planned.scenes), 'scene')}, "
          f"{_count(states, 'state')}, {_count(states, 'key')}, {_count(moves, 'move')}, {_count(states + moves, 'shot')}")
    print()
    print(f"{'scene':<13}{'states':>6}{'moves out':>12}")
    for name in planned.scenes:
        print(f"{name:<13}{per_scene[name]:>6}{out[name]:>12}")
    print()
    _warn(warnings)
    print(f"0 errors, {_count(len(warnings), 'warning')}")
    return 0


def _warn(warnings: tuple[ScreenplayError, ...]) -> None:
    for warning in warnings:
        print(warning.report("warning"), file=sys.stderr)


def print_shots(args) -> int:
    found = project.find(Path.cwd())
    planned = _planned(found)
    told, warnings = _told(found, planned, args.story, _listing(found, None))
    _warn((*planned.warnings, *warnings))
    shots = planned.shots
    if args.state:
        names = [key.state.name for key in planned.keys]
        if args.state not in names:
            close = sorted(get_close_matches(args.state, names, n=3), key=names.index)
            raise ProjectError(f'the app has no state "{args.state}"' +
                               (f"; the closest are {', '.join(close)}" if close else ""))
        shots = [shot for shot in shots if (shot.state if isinstance(shot, Key) else shot.start).name == args.state]
    prompts = [(shot, story.prompt(shot, told)) for shot in shots]
    width = max(len(str(clause.source)) for _, clauses in prompts for clause in clauses)
    print("\n\n".join("\n".join([shot.title, *(f"  {str(clause.source):<{width}}  {clause.text}" for clause in clauses)])
                      for shot, clauses in prompts))
    return 0


def explain(args) -> int:
    print(errors.explain(args.code))
    return 0


def positive(text: str) -> int:
    if (value := int(text)) < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def _tape(found: Project, name: str | None, out: str | None) -> Path:
    """The tape a command works on: the one --out names, or else the story's own, tapes/<story> in the project."""
    return Path(out) if out else found.root / "tapes" / name


def render_tape(args) -> int:
    found = project.find(Path.cwd())
    listing = _listing(found, args.model)
    if listing is None:
        raise ProjectError("no model to render with; pass --model, or set model in [tool.videotape]")
    planned = _planned(found)
    told, warnings = _told(found, planned, args.story, listing)
    _warn((*planned.warnings, *warnings))
    tape = _tape(found, told.name, args.out)
    model, eye = listing.model(), listing.eye(tape)
    if model.price and (calls := uncached(planned, told, model, args.takes, tape)):
        print(model.price.estimate(model.name, calls), flush=True)
    result = render(planned, told, model, eye, tape, ledger.of(found.root, tape), made(found, told, model),
                    takes=args.takes)
    for number, filmed in enumerate(result.shots, 1):
        status = f"rendered {_count(filmed.rendered, 'take')}" if filmed.rendered else "cached"
        print(f"{number}. {filmed.shot.title}  {status}, kept take {filmed.kept.seed}")
    print(f"rendered {sum(bool(filmed.rendered) for filmed in result.shots)} of {_count(len(result.shots), 'shot')}"
          f" -> {errors.shown(tape)}")
    failures = [f"{number}. {filmed.shot.title}  kept take {filmed.kept.seed} fails {item.name}: {item.result}"
                for number, filmed in enumerate(result.shots, 1) for item in filmed.kept.checks.failures]
    for failure in failures:
        print(f"fail: {failure}", file=sys.stderr)
    return 1 if failures else 0


def rewrite_dailies(args) -> int:
    found = project.find(Path.cwd())
    tape = _tape(found, args.story, args.out)
    if not (tape / "dailies.json").is_file():
        raise ChecksError(f"no dailies.json in {errors.shown(tape)}; render the screenplay first")
    dailies.write(tape, dailies.read(tape), ledger.of(found.root, tape).totals())
    print(f"wrote {errors.shown(tape / 'dailies.html')} with {json.dumps(dailies.read(tape)['ledger'])}")
    return 0


def _manifest(tape: str) -> dict:
    """A tape's tape.json, which says what made it."""
    file = Path(tape) / "tape.json"
    if not file.is_file():
        raise ChecksError(f"no tape.json in {tape}; render the screenplay first")
    manifest = json.loads(file.read_text())
    if "made" not in manifest:
        raise ChecksError(f"{file} does not say what made it; render the tape again")
    return manifest


def diff_tapes(args) -> int:
    a, b = _manifest(args.a), _manifest(args.b)
    rows = [(tape, manifest["made"]["label"], manifest["made"]["id"]) for tape, manifest in ((args.a, a), (args.b, b))]
    widths = [max(map(len, column)) for column in zip(*rows)]
    for row in rows:
        print("  ".join(f"{cell:<{width}}" for cell, width in zip(row, widths)))
    app, other = a["made"]["app"], b["made"]["app"]
    print("same app" if (app["code"], app["data"]) == (other["code"], other["data"]) else "another app")
    print("same story" if a["made"]["story"]["hash"] == b["made"]["story"]["hash"] else "another story")
    for part, noun in (("scenes", "state"), ("moves", "move")):
        print(f"{_count(len(a[part].keys() & b[part].keys()), noun)} shared, of {len(a[part])} and {len(b[part])}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="videotape", description="Run in an app's project, the folder whose "
                                     "pyproject.toml names its screenplay in [tool.videotape].")
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan", help="walk every state the app can reach, before anything renders")
    planning.add_argument("--story", help="also check this story, which is stories/<story>.toml in the project")
    planning.add_argument("--model", choices=sorted(MODELS), help="the model whose prompt limit the story is checked "
                          "against (default: model in [tool.videotape])")
    planning.set_defaults(run=plan_app)
    showing = commands.add_parser("shots", help="print every shot's prompt in a story, with the source of each clause")
    showing.add_argument("--story", required=True, help="the story, which is stories/<story>.toml in the project")
    showing.add_argument("--state", help="only this state's key and the moves that leave it, as in \"home()\"")
    showing.set_defaults(run=print_shots)
    explaining = commands.add_parser("explain", help="print an error code's long form, with an example and its fix")
    explaining.add_argument("code", choices=sorted(CODES))
    explaining.set_defaults(run=explain)
    rendering = commands.add_parser("render", help="render the app in a story into a tape: a key per state and a "
                                    "move per action")
    rendering.add_argument("--story", required=True, help="the story, which is stories/<story>.toml in the project")
    rendering.add_argument("--model", choices=sorted(MODELS), help="the model to render with (default: model in "
                           "[tool.videotape])")
    rendering.add_argument("--takes", type=positive, default=3, help="takes per shot; the best by its checks is kept (default 3)")
    rendering.add_argument("--out", help="the tape directory to write (default: tapes/<story> in the project)")
    rendering.set_defaults(run=render_tape)
    rewriting = commands.add_parser("dailies", help="rewrite a tape's dailies page from its record and the ledger")
    which = rewriting.add_mutually_exclusive_group(required=True)
    which.add_argument("--story", help="the story whose tape it is, tapes/<story> in the project")
    which.add_argument("--out", help="the tape directory, for a tape that render wrote with --out")
    rewriting.set_defaults(run=rewrite_dailies)
    diffing = commands.add_parser("diff", help="say whether two tapes are of the same app and the same story, and how "
                                  "many states and moves they share")
    diffing.add_argument("a", help="a tape directory")
    diffing.add_argument("b", help="another tape directory")
    diffing.set_defaults(run=diff_tapes)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except ScreenplayError as error:
        print(error.report(), file=sys.stderr)
        return 1
    except (ProjectError, FfmpegError, ChecksError, WanError, FalError, StandInError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
