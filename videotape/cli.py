import argparse
import json
import sys
from pathlib import Path

from videotape import dailies, frames
from videotape.checks import ChecksError, score
from videotape.eyes import CHECKS
from videotape.frames import FfmpegError
from videotape.loader import load
from videotape.model import MODELS
from videotape.render import render
from videotape.screenplay import ScreenplayError
from videotape.shots import plan
from videotape.wan import WanError


def shots(args) -> int:
    screenplay = load(args.directory)
    planned = plan(screenplay)
    print(screenplay.title)
    for number, shot in enumerate(planned, 1):
        print(f"\n{number}. {shot.title}  ({shot.mode.value})")
        print(f"   {shot.prompt}")
    return 0


def positive(text: str) -> int:
    if (value := int(text)) < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def render_tape(args) -> int:
    result = render(args.directory, MODELS[args.model](), CHECKS[args.checks](Path(args.directory) / "tape"), takes=args.takes)
    for number, filmed in enumerate(result.shots, 1):
        status = f"rendered {filmed.rendered} take{'s' if filmed.rendered > 1 else ''}" if filmed.rendered else "cached"
        print(f"{number}. {filmed.shot.title}  {status}, kept take {filmed.kept.seed}")
    print(f"rendered {sum(bool(filmed.rendered) for filmed in result.shots)} of {len(result.shots)} shots -> {result.tape}")
    failures = [f"{number}. {filmed.shot.title}  kept take {filmed.kept.seed} fails {item.name}: {item.result}"
                for number, filmed in enumerate(result.shots, 1) for item in filmed.kept.checks.failures]
    for failure in failures:
        print(f"fail: {failure}", file=sys.stderr)
    return 1 if failures else 0


def check_tape(args) -> int:
    tape = Path(args.tape)
    if not (tape / "tape.json").is_file():
        raise ChecksError(f"no tape.json in {tape}; render the screenplay first, then pass its tape directory")
    if not (tape / "dailies.json").is_file():
        raise ChecksError(f"no dailies.json in {tape}; render the screenplay again to write it")
    eye = CHECKS[args.checks](tape)
    record = dailies.read(tape)
    if not isinstance(record.get("keys"), list):
        raise ChecksError(f"{tape / 'dailies.json'} is from an older render; render the screenplay again to write it")
    screenplay = load(tape.parent)
    scenes = json.loads((tape / "tape.json").read_text())["scenes"]
    scored, failures = {}, []
    for name, scene in screenplay.scenes.items():
        if name not in scenes:
            raise ChecksError(f'scene "{name}" is not in {tape / "tape.json"}; render the screenplay again')
        key = scenes[name]["key"]
        found = score(frames.read_png(tape / key), scene, eye)
        print(f"{name}  {key}")
        for item in found.items():
            print(f"  {item.name}  {item.result}")
        failures += [f"{name}  {item.name}: {item.result}" for item in found.failures]
        scored[name] = found
    dailies.write(tape, dailies.rescored(record, eye.name, scored))
    print(f"checked {len(scored)} keys with {eye.name}, {f'{len(failures)} failing' if failures else 'all passing'}"
          f" -> {tape / 'dailies.html'}")
    for failure in failures:
        print(f"fail: {failure}", file=sys.stderr)
    return 1 if failures else 0


def rewrite_dailies(args) -> int:
    tape = Path(args.directory) / "tape"
    if not (tape / "dailies.json").is_file():
        raise ChecksError(f"no dailies.json in {tape}; render the screenplay first")
    dailies.write(tape, dailies.read(tape))
    print(f"wrote {tape / 'dailies.html'} with {json.dumps(dailies.read(tape)['ledger'])}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="videotape")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("shots", help="list the shots a screenplay renders into")
    listing.add_argument("directory")
    listing.set_defaults(run=shots)
    rendering = commands.add_parser("render", help="render a screenplay into a tape of clips")
    rendering.add_argument("directory")
    rendering.add_argument("--model", required=True, choices=sorted(MODELS))
    rendering.add_argument("--checks", default="stand-in", choices=sorted(CHECKS))
    rendering.add_argument("--takes", type=positive, default=3, help="takes per shot; the best by its checks is kept (default 3)")
    rendering.set_defaults(run=render_tape)
    checking = commands.add_parser("check", help="read every key of a rendered tape and score it against its scene")
    checking.add_argument("tape")
    checking.add_argument("--checks", default="stand-in", choices=sorted(CHECKS))
    checking.set_defaults(run=check_tape)
    rewriting = commands.add_parser("dailies", help="rewrite a tape's dailies page from its record and ledger")
    rewriting.add_argument("directory")
    rewriting.set_defaults(run=rewrite_dailies)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (ScreenplayError, FfmpegError, ChecksError, WanError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
