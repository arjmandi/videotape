import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from videotape import project, story
from videotape.cli import main
from videotape.errors import CODES
from videotape.plan import Plan, Shot, plan
from videotape.story import Story

FIXTURES = Path(__file__).parent / "fixtures"
CONTRAIL = Path(__file__).parent.parent / "examples" / "contrail"
VIDEOTAPE = Path(sys.executable).with_name("videotape")

# A test edits a screenplay and loads it again within a second, which a cached .pyc would hide.
sys.dont_write_bytecode = True
# videotape dailies opens the page with webbrowser, and true opens nothing.
os.environ["BROWSER"] = "true"


def forget(found: project.Project) -> None:
    """Drop a project's modules, so a copy or an edit of the project is imported afresh."""
    top = found.screenplay.partition(":")[0].partition(".")[0]
    for name in [name for name in sys.modules if name == top or name.startswith(f"{top}.")]:
        del sys.modules[name]


def planned(directory: Path) -> Plan:
    found = project.find(directory)
    forget(found)
    return plan(found.load(), found.max_states)


def told(directory: Path, name: str = "chalk") -> Story:
    """A project's story. chalk is the cafe fixture's."""
    return story.named(directory, name)


def a_story(scenes: dict[str, str] | None = None, elements: dict[str, str] | None = None,
            moves: dict[str, str] | None = None) -> Story:
    """A story that is only a look, for an app made up in a test, with whatever else the test gives it."""
    return Story("plain", "1.0.0", "A plain room.", scenes or {}, elements or {}, moves or {}, Path("plain.toml"), "")


def words(shot: Shot, told: Story) -> str:
    """The prompt a story gives a shot, as the model is sent it."""
    return story.text(story.prompt(shot, told))


def copy_of(fixture: str, to: Path) -> Path:
    """A fresh copy of a fixture project, without anything a render left in it."""
    return Path(shutil.copytree(FIXTURES / fixture, to / fixture,
                                ignore=shutil.ignore_patterns("tape*", "ledger.jsonl", "__pycache__")))


def videotape(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the installed videotape command in a project, the way a developer does."""
    return subprocess.run([str(VIDEOTAPE), *arguments], cwd=directory, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
                               "BROWSER": "true"})


VARIES = re.compile(r"(?P<shot>(?<=^error VT\d{3} ).+?(?= take \d|: ))|(?P<ffmpeg>(?<=decode to one frame: ).+$)"
                    r"|(?P<story>(?<=--story )\S+)|(?P<path>\S*/\S*)|(?P<number>(?<![\w.])\d+(?:\.\d+)?)", re.MULTILINE)
WILDCARDS = {"shot": r"(?:(?! take \d).)+", "ffmpeg": r".+", "story": r"\S+", "path": r"\S+",
             "number": r"\d+(?:\.\d+)?"}


def as_explained(code: str) -> re.Pattern[str]:
    """The lines a render prints for a code, as videotape explain shows them in its example and its next step, with
    what differs from run to run left open: the shot, a path and the hash in it, a number, the story a command names,
    and what ffmpeg said."""
    entry = CODES[code]
    example = f"{entry.example}\n{entry.fix}"
    pattern, at = "", 0
    for part in VARIES.finditer(example):
        pattern += re.escape(example[at:part.start()]) + WILDCARDS[part.lastgroup or ""]
        at = part.end()
    return re.compile(f"^{pattern}{re.escape(example[at:])}$", re.MULTILINE)


@pytest.fixture
def cli(monkeypatch):
    """Run videotape's main in a project, in this process, so a test can swap the model it renders with."""
    def run(directory: Path, *arguments: str) -> int:
        monkeypatch.chdir(directory)
        forget(project.find(directory))
        return main(list(arguments))
    return run
