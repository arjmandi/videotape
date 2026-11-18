"""README.md is the developer's guide. Every file it shows whole is that file of examples/contrail, byte for byte, and
its commands run in order, each printing what the guide shows of it.

The commands start in the project videotape new writes. From the guide's first whole file on, they run in that project
with examples/contrail copied over it, since the guide has the reader write Contrail's files there, and with the
stand-in as its model, as part 2 sets it. The stand-in is made to fail the key of the state the guide retakes and
of the state it accepts, so that both commands act on a real failure. torch is not installed, as in a project new
wrote, which leaves out videotape's qwen extra."""

import dataclasses
import hashlib
import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import CONTRAIL, contrail_copy, planned, told
from videotape import dailies, player, project, qwen, standin, story
from videotape.cli import main
from videotape.plan import Shot
from videotape.standin import Flaw

ROOT = CONTRAIL.parent.parent
GUIDE = ROOT / "README.md"
FENCE = re.compile(r"^```(?P<info>[^\n]*)\n(?P<text>.*?)^```$", re.M | re.S)
VIDEOTAPE = ["uv", "run", "videotape"]
FLAWS = {"VT502": Flaw.MISSPELL, "VT503": Flaw.EXTRA_BOX}
"""The stand-in's flaw that fails a key with each code the guide accepts."""
VARIES = re.compile(r"(?P<hash>\b[0-9a-f]{64}\b)|(?P<path>\S*/\S*)|(?P<number>(?<![\w.])\d+(?:\.\d+)*)")
WILDCARDS = {"hash": r"[0-9a-f]{64}", "path": r"\S+", "number": r"\d+(?:\.\d+)*"}
BUNDLE = "dev.videotape.TapePlayer"
CONTRAIL_MODEL = tomllib.loads((CONTRAIL / "pyproject.toml").read_text())["tool"]["videotape"]["model"]


@dataclass(frozen=True)
class Block:
    info: str
    text: str
    line: int
    follows: bool
    """Whether only blank lines stand between this block and the one before it."""

    @property
    def language(self) -> str:
        return self.info.partition(" ")[0]

    @property
    def file(self) -> str | None:
        """The project file a block shows whole, which its fence names, as in ```python title=contrail/data.py."""
        named = re.search(r"\btitle=(\S+)", self.info)
        return named[1] if named else None


@dataclass(frozen=True)
class Step:
    command: str
    line: int
    shown: str | None = None
    """What the guide shows the command printing: the text block right after the command's sh block, whose last
    command it is."""

    @property
    def words(self) -> list[str]:
        return shlex.split(self.command)

    def option(self, name: str) -> str | None:
        words = self.words
        return words[words.index(name) + 1] if name in words else None


@dataclass(frozen=True)
class Ran:
    step: Step
    code: int
    tape: Path
    record: dict | None
    """The tape's dailies.json after the step, when the step names a story whose tape has one."""


def blocks(markdown: str) -> list[Block]:
    found, end = list[Block](), None
    for match in FENCE.finditer(markdown):
        follows = end is not None and not markdown[end:match.start()].strip()
        found.append(Block(match["info"].strip(), match["text"], markdown.count("\n", 0, match.start()) + 1, follows))
        end = match.end()
    return found


def walk(markdown: str) -> list[Step | Block]:
    """The guide's commands and whole files, in the order a reader meets them."""
    found = list[Step | Block]()
    previous: Block | None = None
    for block in blocks(markdown):
        if block.file:
            found.append(block)
        elif block.language == "sh":
            found += [Step(command, block.line + number) for number, command in enumerate(block.text.splitlines(), 1)]
        elif block.language == "text" and block.follows and previous and previous.language == "sh":
            found[-1] = dataclasses.replace(found[-1], shown=block.text)
        previous = block
    return found


def steps() -> list[Step]:
    return [event for event in walk(GUIDE.read_text()) if isinstance(event, Step)]


def videotape_command(step: Step, name: str) -> list[str] | None:
    """The arguments of a uv run videotape command of that name, or None for any other command."""
    words = step.words
    return words[len(VIDEOTAPE):] if words[:len(VIDEOTAPE)] == VIDEOTAPE and words[3:4] == [name] else None


def pattern(line: str) -> re.Pattern[str]:
    """A line the guide shows, with what differs from run to run or machine to machine left open: a path and a number."""
    built, at = "", 0
    for part in VARIES.finditer(line):
        built += re.escape(line[at:part.start()]) + WILDCARDS[part.lastgroup or ""]
        at = part.end()
    return re.compile(built + re.escape(line[at:]))


def missing(shown: str, said: str) -> list[str]:
    """The lines the guide shows that the command did not print. A line of ... stands for lines the guide leaves out,
    and lines that print at once may print in any order."""
    printed = [line.rstrip() for line in said.splitlines()]
    return [line for line in shown.splitlines() if line.strip() and line.strip() != "..."
            and not any(pattern(line.rstrip()).fullmatch(out) for out in printed)]


def failing(shown: str | None) -> bool:
    """Whether the output the guide shows says that something fails, and so that the command exits 1."""
    return bool(shown and re.search(r"^fail\b", shown, re.M))


def flawed(guide: list[Step]) -> Callable[[bytes, int, list[Flaw]], Flaw]:
    """The stand-in's flaws for the guide. The key of the state the guide retakes is misspelt on the render's takes and
    clean on the retake's, and the key of the state it accepts fails the accepted code on every take. Every other take
    of Contrail in a story the guide renders is clean, so that its render films each shot once, and every take of the
    starter has the stand-in's own flaw, as a reader's has. Each prompt comes from Contrail's plan and story."""
    plan, takes, default = planned(CONTRAIL), project.find(CONTRAIL).takes, standin._default_flaw

    def prompt(shot: Shot, name: str) -> str:
        return story.text(story.prompt(shot, told(CONTRAIL, name)))

    def key(arguments: list[str]) -> str:
        state = next(key for key in plan.keys if key.state.name == arguments[1])
        return prompt(state, arguments[arguments.index("--story") + 1])

    [retaken] = [key(arguments) for step in guide if (arguments := videotape_command(step, "retake"))]
    [(accepted, code)] = [(key(arguments), arguments[2]) for step in guide
                          if (arguments := videotape_command(step, "accept"))]
    stories = {arguments[arguments.index("--story") + 1] for step in guide
               if (arguments := videotape_command(step, "render"))} - {"starter"}

    # The stand-in gives its default flaw only the hash of a take's seed and prompt, so a take is told by that hash.
    def hashed(seed: int, words: str) -> bytes:
        return hashlib.sha256(f"{seed}\n{words}".encode()).digest()

    contrail = {hashed(seed, prompt(shot, name)) for name in stories for shot in plan.shots for seed in range(1, takes + 1)}

    def flaw(digest: bytes, seed: int, kinds: list[Flaw]) -> Flaw:
        if digest == hashed(seed, retaken) and seed <= takes:
            return Flaw.MISSPELL
        if digest == hashed(seed, accepted):
            return FLAWS[code]
        return Flaw.NONE if digest in contrail else default(digest, seed, kinds)
    return flaw


def subcommands(capsys) -> set[str]:
    with pytest.raises(SystemExit):
        main(["--help"])
    usage = capsys.readouterr().out
    return set(re.search(r"\{([\w,-]+)\}", usage)[1].split(","))


def quit_player() -> bool:
    """Wait up to 30 s for TapePlayer to run, then quit it by its bundle id. False when it never ran."""
    for _ in range(60):
        asked = subprocess.run(["osascript", "-e", f'return application id "{BUNDLE}" is running'],
                               capture_output=True, text=True)
        if asked.stdout.strip() == "true":
            subprocess.run(["osascript", "-e", f'tell application id "{BUNDLE}" to quit'], check=True)
            return True
        time.sleep(0.5)
    return False


def contrail_over(folder: Path) -> None:
    """Write examples/contrail over the reader's project, with videotape from this checkout by its absolute path."""
    contrail_copy(folder)
    pyproject = folder / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('path = "../.."', f'path = "{ROOT}"')
                         .replace(f'model = "{CONTRAIL_MODEL}"', 'model = "stand-in"'))


def test_every_file_the_guide_shows_whole_is_contrails_byte_for_byte():
    shown = [event for event in walk(GUIDE.read_text()) if isinstance(event, Block)]
    for block in shown:
        assert (CONTRAIL / block.file).is_file(), f"README.md:{block.line} shows {block.file}, which examples/contrail lacks"
        assert block.text == (CONTRAIL / block.file).read_text(), f"README.md:{block.line} is not {block.file}"
    written = {path.relative_to(CONTRAIL).as_posix() for pattern in ("contrail/*.py", "stories/*.toml")
               for path in CONTRAIL.glob(pattern) if path.read_text()}
    assert written == {block.file for block in shown}


def test_the_guide_ends_by_setting_the_model_contrail_renders_with():
    assert f'set `model = "{CONTRAIL_MODEL}"` in `pyproject.toml`' in GUIDE.read_text()


def test_the_guide_runs_from_new_and_leaves_publish_for_last():
    guide = steps()
    assert guide[0].words[:2] == ["uvx", "--from"] and guide[0].words[3:] == ["videotape", "new", "contrail"]
    assert [step.command for step in guide if videotape_command(step, "publish")] == [guide[-1].command]


@pytest.mark.parametrize("real_player", [False, pytest.param(True, marks=pytest.mark.player)],
                         ids=["player-faked", "player-real"])
def test_the_guides_commands_run_in_order_and_print_what_it_shows(real_player, tmp_path, cli, capsys, monkeypatch):
    guide = steps()
    monkeypatch.setattr(standin, "_default_flaw", flawed(guide))
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    real = qwen.distribution

    def without_torch(name: str):
        if name == "torch":
            raise qwen.PackageNotFoundError(name)
        return real(name)
    monkeypatch.setattr(qwen, "distribution", without_torch)
    monkeypatch.setitem(sys.modules, "torch", None)
    opened = list[list[str]]()
    if not real_player:
        monkeypatch.setattr(player, "_launch", opened.append)
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")}
    here, written, ran = tmp_path, False, list[Ran]()
    for event in walk(GUIDE.read_text()):
        if isinstance(event, Block):
            if not written:
                contrail_over(here)
                written = True
            continue
        step = event
        words = step.words
        if words[0] == "cd":
            here = here / words[1]
            continue
        if words[0] == "uvx":
            code, said = cli(here, *words[words.index("videotape") + 1:]), "".join(capsys.readouterr())
        elif words[:len(VIDEOTAPE)] == VIDEOTAPE:
            code, said = cli(here, *words[len(VIDEOTAPE):]), "".join(capsys.readouterr())
        else:
            finished = subprocess.run(words, cwd=here, env=environment, capture_output=True, text=True)
            code, said = finished.returncode, finished.stdout + finished.stderr
        where = f"README.md:{step.line} {step.command}"
        assert code == int(failing(step.shown)), f"{where} exited with {code}:\n{said}"
        assert not missing(step.shown or "", said), f"{where} did not print {missing(step.shown or '', said)}:\n{said}"
        if real_player and videotape_command(step, "play"):
            assert quit_player(), f"{where} exited, and TapePlayer did not run within 30 s"
        tape = here / "tapes" / (step.option("--story") or "")
        ran.append(Ran(step, code, tape, dailies.read(tape) if (tape / "dailies.json").is_file() else None))

    [retake] = [index for index, done in enumerate(ran) if videotape_command(done.step, "retake")]
    [accept] = [index for index, done in enumerate(ran) if videotape_command(done.step, "accept")]
    titles = {key.state.name: key.title for key in planned(CONTRAIL).keys}
    retaken = titles[videotape_command(ran[retake].step, "retake")[1]]
    _, state, code = videotape_command(ran[accept].step, "accept")[:3]
    accepted = titles[state]
    failed = next(done.record for done in ran if videotape_command(done.step, "render") and done.tape == ran[retake].tape)
    assert {failure["shot"] for failure in failed["failures"]} == {retaken, accepted}
    assert (accepted, code) in {(failure["shot"], failure["code"]) for failure in failed["failures"]}
    after = ran[retake].record
    [kept] = [take for shot in after["keys"] if shot["title"] == retaken for take in shot["takes"] if take["kept"]]
    assert kept["seed"] > after["takes"] and retaken not in {failure["shot"] for failure in after["failures"]}
    assert [(entry["shot"], entry["code"]) for entry in ran[accept].record["accepted"]] == [(accepted, code)]
    rendered = next(done for done in ran[accept + 1:]
                    if videotape_command(done.step, "render") or videotape_command(done.step, "retake"))
    assert rendered.code == 0
    assert [(failure["shot"], bool(failure["accepted"])) for failure in rendered.record["failures"]] == [(accepted, True)]
    if not real_player:
        assert opened == [["open", str(player.built()), "--args", str(done.tape.resolve())]
                          for done in ran if videotape_command(done.step, "play")]
