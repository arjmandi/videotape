import argparse
import json
import shlex
import sys
import webbrowser
from collections import Counter
from difflib import get_close_matches
from pathlib import Path

from videotape import dailies, doctor, errors, ledger, new, player, project, publish, story
from videotape.errors import CODES, RenderError, ScreenplayError
from videotape.made import finished, made, manifest, model_named
from videotape.model import MODELS, Listing, estimate
from videotape.plan import Key, Plan, Shot, plan
from videotape.project import Project
from videotape.render import Filmed, render
from videotape.story import Story


def _planned(found: Project) -> Plan:
    return plan(found.load(), found.max_states)


def _listing(found: Project, named: str | None) -> Listing | None:
    """The model a command names, or else the project's, or none when neither names one."""
    name = named or found.model
    return MODELS[name] if name else None


def _told(found: Project, planned: Plan, name: str,
          listing: Listing | None) -> tuple[Story, tuple[ScreenplayError, ...]]:
    """The project's story of this name, checked against the plan and the model, with the warnings of that check."""
    told = story.named(found.root, name)
    return told, story.check(told, planned, listing.prompt_limit if listing else None)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def _warn(warnings: tuple[ScreenplayError, ...]) -> None:
    for warning in warnings:
        print(warning.report("warning"), file=sys.stderr)


def plan_app(args) -> int:
    found = project.find(Path.cwd())
    if args.model and not args.story:
        raise ScreenplayError("VT310", "--model", "names the model whose prompt limit a story's prompts must fit, and "
                              "no --story names one", f"name the story too, as in videotape plan --story starter "
                              f"--model {args.model}")
    planned, listing = _planned(found), _listing(found, args.model)
    warnings, in_story = planned.warnings, ""
    if args.story:
        told, more = _told(found, planned, args.story, listing)
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
    if listing:
        print(estimate(args.model or found.model, listing, len(planned.shots), len(planned.keys), found.takes))
    return 0


def _unnamed(name: str, what: str, close: list[str]) -> ScreenplayError:
    """VT212 for a name no state or move has, with the closest names."""
    return ScreenplayError("VT212", f'"{name}"', f"the app has no {what} of this name",
                           f"name one of the closest: {', '.join(close)}" if close else
                           'name a state as the plan names it, as in "home()", or a move by its two states, as in '
                           '"home() -> search()"')


def _shot_named(planned: Plan, name: str) -> Shot:
    """The one shot a name picks out: a state's key, a move as "<state> -> <state>", or a move by its full title.
    VT212 for a name that picks out none, with the closest, or two moves, with their full titles."""
    names = {key.state.name: [key] for key in planned.keys}
    for move in planned.moves:
        names.setdefault(f"{move.start.name} -> {move.land.name}", []).append(move)
        names[move.title] = [move]
    if name not in names:
        raise _unnamed(name, "state or move", get_close_matches(name, names, n=3))
    if len(shots := names[name]) > 1:
        raise ScreenplayError("VT212", f'"{name}"', f"names {_count(len(shots), 'move')}",
                              "name one by its full title: " + "; ".join(shot.title for shot in shots))
    return shots[0]


def print_shots(args) -> int:
    found = project.find(Path.cwd())
    planned = _planned(found)
    told, warnings = _told(found, planned, args.story, _listing(found, None))
    _warn((*planned.warnings, *warnings))
    shots = planned.shots
    if args.state:
        names = [key.state.name for key in planned.keys]
        if args.state not in names:
            raise _unnamed(args.state, "state", sorted(get_close_matches(args.state, names, n=3), key=names.index))
        shots = [shot for shot in shots if (shot.state if isinstance(shot, Key) else shot.start).name == args.state]
    prompts = [(shot, story.prompt(shot, told)) for shot in shots]
    width = max(len(str(clause.source)) for _, clauses in prompts for clause in clauses)
    print("\n\n".join("\n".join([shot.title, *(f"  {str(clause.source):<{width}}  {clause.text}" for clause in clauses)])
                      for shot, clauses in prompts))
    return 0


def new_project(args) -> int:
    folder = new.project(args.name, Path.cwd())
    print(f"made {errors.shown(folder)}: a screenplay of two scenes, a data table, and the story starter\nnext:")
    for step in (f"cd {shlex.quote(errors.shown(folder))}", "uv run videotape doctor",
                 "uv run videotape render --story starter --model stand-in", "uv run videotape play --story starter"):
        print(f"  {step}")
    return 0


def doctor_checks(args) -> int:
    results = doctor.checks(Path.cwd())
    for check in results:
        print(check)
    return 0 if all(check.ok for check in results) else 1


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


def _rendering(story: str | None, out: str | None) -> str:
    """The command that renders a tape: the story's own, or the one --out names, which names no story."""
    return " ".join(["videotape", "render", "--story", shlex.quote(story) if story else "<story>",
                     *(["--out", shlex.quote(out)] if out else [])])


def _resume(args, story: str) -> str:
    """The render command that resumes this one."""
    words = ["videotape", "render", "--story", story]
    for flag in ("model", "takes", "out"):
        if getattr(args, flag, None):
            words += [f"--{flag}", str(getattr(args, flag))]
    if getattr(args, "cap_usd", None) is not None:
        words += ["--cap-usd", f"{args.cap_usd:.2f}"]
    return shlex.join(words)


def _render(found: Project, args) -> int:
    """Render the story's tape with the project's or the named model, print a line per shot as it finishes, the
    totals, and each failing shot with what to run next."""
    listing = _listing(found, args.model)
    if listing is None:
        raise ScreenplayError("VT110", errors.shown(found.root / "pyproject.toml"), "[tool.videotape] names no model, "
                              "and neither does --model", 'set it in [tool.videotape], as in model = "stand-in", or name '
                              f"one for this render, as in videotape render --story {args.story} --model stand-in")
    planned = _planned(found)
    told, warnings = _told(found, planned, args.story, listing)
    _warn((*planned.warnings, *warnings))
    tape = _tape(found, told.name, args.out)
    model, takes = listing.model(), args.takes or found.takes
    readers = [reader(tape) for reader in listing.readers]
    cap = args.cap_usd if args.cap_usd is not None else found.cap_usd
    book = ledger.of(found.root, tape)
    if listing.price or any(reader.paid for reader in readers):
        print(f"{estimate(model.name, listing, len(planned.shots), len(planned.keys), takes)}, "
              f"{f'cap ${cap:.2f}' if cap is not None else 'no cap'}, ${book.totals()['usd']:.2f} spent", flush=True)
    numbers = {shot: number for number, shot in enumerate(planned.shots, 1)}

    def report(filmed: Filmed) -> None:
        for error in filmed.reported:
            print(error.report(), file=sys.stderr, flush=True)
        verdict = "passed" if filmed.passed else f"fails {' '.join(sorted({f.code for f in filmed.failures}))}"
        filmed_takes = f"{_count(filmed.rendered, 'take')} filmed" if filmed.rendered else "cached"
        print(f"{numbers[filmed.shot]}. {filmed.shot.title}  kept take {filmed.kept.seed}, {verdict}, {filmed_takes}, "
              f"${filmed.usd:.2f}, {filmed.seconds:.1f} s", flush=True)

    result = render(planned, told, model, readers, tape, book, made(found, told, model), takes=takes, limit=listing.limit,
                    price=listing.price, cap=cap, resume=_resume(args, told.name), report=report)
    record = dailies.read(tape)
    print(f"{_count(len(result.shots), 'shot')}, {_count(sum(f.rendered for f in result.shots), 'take')} filmed, "
          f"${sum(f.usd for f in result.shots):.2f}, {result.seconds:.1f} s, tape {record['tape']['bytes'] / 1e6:.1f} MB"
          f" -> {errors.shown(tape)}", flush=True)
    failing = 0
    for failure in record["failures"]:
        line = f"{numbers[next(s for s in planned.shots if s.title == failure['shot'])]}. {failure['shot']}  " \
               f"{failure['code']} {failure['about']}: {failure['evidence']}"
        if failure["accepted"]:
            print(f"accepted: {line}\n  reason: {failure['accepted']['reason']}", file=sys.stderr)
        else:
            failing += 1
            print(f"fail: {line}\n  next: {failure['next']['retake']}", file=sys.stderr)
    return 1 if failing else 0


def render_tape(args) -> int:
    return _render(project.find(Path.cwd()), args)


def retake(args) -> int:
    """Film new takes of a shot with the model that made the tape, with seeds after the highest it has tried, and
    render again so the best of all its takes is kept and the moves pinned to a key that changed are drawn again."""
    found = project.find(Path.cwd())
    planned = _planned(found)
    shot = _shot_named(planned, args.shot)
    tape, rendering = _tape(found, args.story, args.out), _rendering(args.story, args.out)
    record = dailies.recorded(tape, rendering)
    args.model = model_named(manifest(tape, rendering), tape, rendering)
    tried = [take["seed"] for filmed in (*record["keys"], *record["moves"]) if filmed["title"] == shot.title
             for take in filmed["takes"]]
    retakes = record.get("retakes", {})
    highest = max([record["takes"], *tried, *retakes.get(shot.title, [])])
    retakes[shot.title] = [*retakes.get(shot.title, []), *range(highest + 1, highest + 1 + args.takes)]
    dailies.write(tape, {**record, "retakes": retakes}, ledger.of(found.root, tape).totals())
    print(f"retaking {shot.title} with seed{'s' if args.takes > 1 else ''} "
          f"{', '.join(map(str, retakes[shot.title][-args.takes:]))}", flush=True)
    # The render keeps the limit the tape was rendered with, so a retake changes only the shot it names.
    args.takes = record["takes"]
    return _render(found, args)


def accept(args) -> int:
    """Record an accepted failure in the tape's record, when the shot fails with that code. The accept holds for the
    shot's kept take, the one the person looked at."""
    found = project.find(Path.cwd())
    planned = _planned(found)
    shot = _shot_named(planned, args.shot)
    tape = _tape(found, args.story, args.out)
    record = dailies.recorded(tape, _rendering(args.story, args.out))
    failing = [f for f in record["failures"] if (f["shot"], f["code"]) == (shot.title, args.code)]
    if not failing:
        codes = sorted({f["code"] for f in record["failures"] if f["shot"] == shot.title})
        where = f" --out {args.out}" if args.out else ""
        raise ScreenplayError(
            "VT408", shot.title, f"does not fail {args.code}; " + (f"it fails {', '.join(codes)}" if codes else "it passes")
            + ", so nothing is written down",
            f'accept the check it fails: videotape accept "{dailies.named(shot)}" {codes[0]} --story {record["story"]}'
            f'{where} --reason "..."' if codes else "nothing; its kept take passes every check")
    accepted = {"shot": shot.title, "code": args.code, "reason": args.reason, "at": ledger.now(),
                "seed": failing[0]["take"], "clip": failing[0]["clip"]}
    others = [a for a in record.get("accepted", []) if (a["shot"], a["code"]) != (shot.title, args.code)]
    record["accepted"] = [*others, accepted]
    for failure in failing:
        failure.update(dailies.verdict(record["accepted"], shot.title, args.code, failure["clip"]))
    dailies.write(tape, record, ledger.of(found.root, tape).totals())
    print(f"accepted {args.code} on {shot.title}: {args.reason}")
    return 0


def rewrite_dailies(args) -> int:
    found = project.find(Path.cwd())
    tape = _tape(found, args.story, args.out)
    dailies.write(tape, dailies.recorded(tape, _rendering(args.story, args.out)), ledger.of(found.root, tape).totals())
    page = tape / "dailies.html"
    print(f"wrote {errors.shown(page)} with {json.dumps(dailies.read(tape)['ledger'])}")
    webbrowser.open(page.resolve().as_uri())
    return 0


def play(args) -> int:
    found = project.find(Path.cwd())
    tape = _tape(found, args.story, args.out)
    finished(tape, _rendering(args.story, args.out))
    print(shlex.join(player.play(tape)))
    return 0


def publish_app(args) -> int:
    found = project.find(Path.cwd())
    done = publish.publish(found, _tape(found, args.story, args.out), _rendering(args.story, args.out))
    print(f"published {errors.shown(done.app)}, {done.size / 1e6:.1f} MB, zipped to {errors.shown(done.zip)}, "
          f"{done.zip.stat().st_size / 1e6:.1f} MB")
    print(f"label {done.label}\nid {done.id}")
    print(f"{publish.LOCK} holds the label now; commit it" if done.locked else f"{publish.LOCK} held the label already")
    return 0


def diff_tapes(args) -> int:
    a, b = (manifest(Path(tape), _rendering(None, None)) for tape in (args.a, args.b))
    rows = [(tape, manifest["made"]["label"], manifest["made"]["id"]) for tape, manifest in ((args.a, a), (args.b, b))]
    widths = [max(map(len, column)) for column in zip(*rows)]
    for row in rows:
        print("  ".join(f"{cell:<{width}}" for cell, width in zip(row, widths)))
    app, other = a["made"]["app"], b["made"]["app"]
    print("same app" if all(app[part] == other[part] for part in ("screenplay", "code", "data")) else "another app")
    print("same story" if a["made"]["story"]["hash"] == b["made"]["story"]["hash"] else "another story")
    for part, noun in (("scenes", "state"), ("moves", "move")):
        print(f"{_count(len(a[part].keys() & b[part].keys()), noun)} shared, of {len(a[part])} and {len(b[part])}")
    return 0


def _tape_flags(command: argparse.ArgumentParser, required: bool = True) -> None:
    which = command.add_mutually_exclusive_group(required=required)
    which.add_argument("--story", help="the story whose tape it is, tapes/<story> in the project")
    which.add_argument("--out", help="the tape's folder, for a tape that render wrote with --out")


def _render_flags(command: argparse.ArgumentParser) -> None:
    command.add_argument("--cap-usd", type=float, help="the most a render may spend on a model that bills per "
                         "call (default: cap_usd in [tool.videotape])")
    command.add_argument("--out", help="the folder to write the tape to (default: tapes/<story> in the project)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="videotape", description="Run in an app's project, the folder whose "
                                     "pyproject.toml names its screenplay in [tool.videotape].")
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan", help="walk every state the app can reach, with the keys and moves a render "
                                   "films")
    planning.add_argument("--story", help="also load this story, which is stories/<story>.toml in the project")
    planning.add_argument("--model", choices=sorted(MODELS), help="the model whose prompt limit the story's prompts "
                          "must fit (default: model in [tool.videotape])")
    planning.set_defaults(run=plan_app)
    showing = commands.add_parser("shots", help="print every shot's prompt in a story, with the source of each clause")
    showing.add_argument("--story", required=True, help="the story, which is stories/<story>.toml in the project")
    showing.add_argument("--state", help="only this state's key and the moves that leave it, as in \"home()\"")
    showing.set_defaults(run=print_shots)
    starting = commands.add_parser("new", help="start an app's project in a new folder: a screenplay of two scenes, "
                                   "a data table, and a story")
    starting.add_argument("name", help="the project's name, which is its folder's and its Python package's")
    starting.set_defaults(run=new_project)
    doctoring = commands.add_parser("doctor", help="say whether this machine has what videotape needs, and in a "
                                    "project, the API key its model needs and what its eye needs")
    doctoring.set_defaults(run=doctor_checks)
    explaining = commands.add_parser("explain", help="print an error code's long form, with an example and its fix")
    explaining.add_argument("code", choices=sorted(CODES))
    explaining.set_defaults(run=explain)
    rendering = commands.add_parser("render", help="render the app in a story into a tape: a key per state and a "
                                    "move per action; a render run again resumes")
    rendering.add_argument("--story", required=True, help="the story, which is stories/<story>.toml in the project")
    rendering.add_argument("--takes", type=positive, help="the most takes a shot gets; it stops at the first that "
                           "passes (default: takes in [tool.videotape], or 4)")
    rendering.add_argument("--model", choices=sorted(MODELS), help="the model that films the takes (default: model "
                           "in [tool.videotape])")
    _render_flags(rendering)
    rendering.set_defaults(run=render_tape)
    retaking = commands.add_parser("retake", help="film new takes of one shot with the model that made the tape, and "
                                   "keep the best of all its takes")
    retaking.add_argument("shot", help='a key, named by its state as in "home()", or a move, as in '
                          '"home() -> search()"')
    retaking.add_argument("--story", required=True, help="the story whose tape it is")
    retaking.add_argument("--takes", type=positive, default=1, help="how many new takes to film (default 1)")
    _render_flags(retaking)
    retaking.set_defaults(run=retake)
    accepting = commands.add_parser("accept", help="mark a failing check as fine, with a reason")
    accepting.add_argument("shot", help='a key, named by its state as in "home()", or a move, as in '
                           '"home() -> search()"')
    accepting.add_argument("code", choices=sorted(code for code in CODES if code[:3] == "VT5"))
    accepting.add_argument("--story", required=True, help="the story whose tape it is")
    accepting.add_argument("--reason", required=True, help="why this failing check is fine")
    accepting.add_argument("--out", help="the tape's folder, for a tape that render wrote with --out")
    accepting.set_defaults(run=accept)
    rewriting = commands.add_parser("dailies", help="rewrite a tape's dailies.html from its dailies.json and the "
                                    "ledger, and open it")
    _tape_flags(rewriting)
    rewriting.set_defaults(run=rewrite_dailies)
    playing = commands.add_parser("play", help="open a tape in TapePlayer, building it first when it needs to")
    _tape_flags(playing)
    playing.set_defaults(run=play)
    publishing = commands.add_parser("publish", help="make a tape into a Mac app in dist/ that plays it, signed ad hoc "
                                     "and zipped, and add it to videotape.lock")
    _tape_flags(publishing)
    publishing.set_defaults(run=publish_app)
    diffing = commands.add_parser("diff", help="say whether two tapes are of the same app and the same story, and how "
                                  "many states and moves they share")
    diffing.add_argument("a", help="a tape's folder")
    diffing.add_argument("b", help="another tape's folder")
    diffing.set_defaults(run=diff_tapes)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (ScreenplayError, RenderError) as error:
        print(error.report(), file=sys.stderr)
        return 1
