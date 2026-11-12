import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from videotape import dailies, errors, ledger, project
from videotape.checks import ChecksError
from videotape.errors import CODES, ScreenplayError
from videotape.fal import FalError
from videotape.frames import FfmpegError
from videotape.model import MODELS
from videotape.plan import Plan, plan
from videotape.project import Project, ProjectError
from videotape.render import render, uncached
from videotape.standin import StandInError
from videotape.wan import WanError


def _planned(found: Project) -> Plan:
    return plan(found.load(), found.max_states)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def plan_app(args) -> int:
    found = project.find(Path.cwd())
    planned = _planned(found)
    states, moves = len(planned.keys), len(planned.moves)
    per_scene = Counter(key.state.scene.name for key in planned.keys)
    out = Counter(move.start.scene.name for move in planned.moves)
    print(f"{' '.join(filter(None, (planned.title, found.version)))}: {_count(len(planned.scenes), 'scene')}, "
          f"{_count(states, 'state')}, {_count(states, 'key')}, {_count(moves, 'move')}, {_count(states + moves, 'shot')}")
    print()
    print(f"{'scene':<13}{'states':>6}{'moves out':>12}")
    for name in planned.scenes:
        print(f"{name:<13}{per_scene[name]:>6}{out[name]:>12}")
    print()
    for warning in planned.warnings:
        print(warning.report("warning"), file=sys.stderr)
    print(f"0 errors, {_count(len(planned.warnings), 'warning')}")
    return 0


def explain(args) -> int:
    print(errors.explain(args.code))
    return 0


def positive(text: str) -> int:
    if (value := int(text)) < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def _tape(found: Project, out: str | None) -> Path:
    return Path(out) if out else found.root / "tape"


def render_tape(args) -> int:
    found = project.find(Path.cwd())
    name = args.model or found.model
    if name is None:
        raise ProjectError("no model to render with; pass --model, or set model in [tool.videotape]")
    if name not in MODELS:
        raise ProjectError(f'[tool.videotape] sets model = "{name}", and the models are {", ".join(sorted(MODELS))}')
    planned = _planned(found)
    tape = _tape(found, args.out)
    model, eye = MODELS[name].model(), MODELS[name].eye(tape)
    if model.price and (calls := uncached(planned, model, args.takes, tape)):
        print(model.price.estimate(model.name, calls), flush=True)
    result = render(planned, model, eye, tape, ledger.of(found.root, tape), takes=args.takes)
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
    tape = _tape(found, args.out)
    if not (tape / "dailies.json").is_file():
        raise ChecksError(f"no dailies.json in {errors.shown(tape)}; render the screenplay first")
    dailies.write(tape, dailies.read(tape), ledger.of(found.root, tape).totals())
    print(f"wrote {errors.shown(tape / 'dailies.html')} with {json.dumps(dailies.read(tape)['ledger'])}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="videotape", description="Run in an app's project, the folder whose "
                                     "pyproject.toml names its screenplay in [tool.videotape].")
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan", help="walk every state the app can reach, before anything renders")
    planning.set_defaults(run=plan_app)
    explaining = commands.add_parser("explain", help="print an error code's long form, with an example and its fix")
    explaining.add_argument("code", choices=sorted(CODES))
    explaining.set_defaults(run=explain)
    rendering = commands.add_parser("render", help="render the app into a tape: a key per state and a move per action")
    rendering.add_argument("--model", choices=sorted(MODELS), help="the model to render with (default: model in "
                           "[tool.videotape])")
    rendering.add_argument("--takes", type=positive, default=3, help="takes per shot; the best by its checks is kept (default 3)")
    rendering.add_argument("--out", help="the tape directory to write (default: tape in the project)")
    rendering.set_defaults(run=render_tape)
    rewriting = commands.add_parser("dailies", help="rewrite a tape's dailies page from its record and the ledger")
    rewriting.add_argument("--out", help="the tape directory (default: tape in the project)")
    rewriting.set_defaults(run=rewrite_dailies)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except ScreenplayError as error:
        print(error.report(), file=sys.stderr)
        return 1
    except (ProjectError, FfmpegError, ChecksError, WanError, FalError, StandInError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
