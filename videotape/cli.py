import argparse
import sys

from videotape.frames import FfmpegError
from videotape.loader import load
from videotape.model import MODELS
from videotape.render import render
from videotape.screenplay import ScreenplayError
from videotape.shots import plan


def shots(args) -> int:
    screenplay = load(args.directory)
    planned = plan(screenplay)
    print(screenplay.title)
    for number, shot in enumerate(planned, 1):
        label = f'  "{shot.label}"' if shot.label else ""
        print(f"\n{number}. {shot.start or 'opening'} -> {shot.land}{label}  ({shot.mode.value})")
        print(f"   {shot.prompt}")
    return 0


def render_tape(args) -> int:
    model, eye = MODELS[args.model]()
    result = render(args.directory, model, eye)
    for number, filmed in enumerate(result.shots, 1):
        status = f"rendered {filmed.rendered} takes" if filmed.rendered else "cached"
        print(f"{number}. {filmed.shot.title}  {status}, kept take {filmed.kept.seed}")
    print(f"rendered {sum(bool(filmed.rendered) for filmed in result.shots)} of {len(result.shots)} shots -> {result.tape}")
    failures = [f"{number}. {filmed.shot.title}  kept take {filmed.kept.seed} fails {item.name}: {item.result}"
                for number, filmed in enumerate(result.shots, 1) for item in filmed.kept.checks.failures]
    for failure in failures:
        print(f"fail: {failure}", file=sys.stderr)
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="videotape")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("shots", help="list the shots a screenplay renders into")
    listing.add_argument("directory")
    listing.set_defaults(run=shots)
    rendering = commands.add_parser("render", help="render a screenplay into a tape of clips")
    rendering.add_argument("directory")
    rendering.add_argument("--model", required=True, choices=sorted(MODELS))
    rendering.set_defaults(run=render_tape)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (ScreenplayError, FfmpegError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
