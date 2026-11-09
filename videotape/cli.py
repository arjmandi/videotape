import argparse
import sys

from videotape.loader import load
from videotape.screenplay import ScreenplayError
from videotape.shots import plan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="videotape")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("shots", help="list the shots a screenplay renders into").add_argument("directory")
    args = parser.parse_args(argv)
    try:
        screenplay = load(args.directory)
        shots = plan(screenplay)
    except ScreenplayError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(screenplay.title)
    for number, shot in enumerate(shots, 1):
        label = f'  "{shot.label}"' if shot.label else ""
        print(f"\n{number}. {shot.start or 'opening'} -> {shot.land}{label}  ({shot.mode.value})")
        print(f"   {shot.prompt}")
    return 0
