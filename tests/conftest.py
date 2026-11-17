import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from videotape import project, story
from videotape.cli import main
from videotape.errors import CODES, ScreenplayError
from videotape.plan import Plan, Shot, plan
from videotape.story import Story

FIXTURES = Path(__file__).parent / "fixtures"
RECORDED = FIXTURES / "recorded"
"""What the paid screen test wrote, copied unchanged: recorded/recorded.txt."""
CONTRAIL = Path(__file__).parent.parent / "examples" / "contrail"
VIDEOTAPE = Path(sys.executable).with_name("videotape")

# A test edits a screenplay and loads it again within a second, which a cached .pyc would hide.
sys.dont_write_bytecode = True
# videotape dailies opens the page with webbrowser, and true opens nothing.
os.environ["BROWSER"] = "true"


def forget(found: project.Project) -> None:
    """Drop a project's modules, and its folder from the import path, so a copy or an edit of the project is imported
    afresh. A regular package anywhere on the path wins over a namespace package before it, so a starter's contrail
    package, left on the path, would stand in for examples/contrail's, which has no __init__.py."""
    top = found.screenplay.partition(":")[0].partition(".")[0]
    for name in [name for name in sys.modules if name == top or name.startswith(f"{top}.")]:
        del sys.modules[name]
    while str(found.root) in sys.path:
        sys.path.remove(str(found.root))


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


LEFT_BEHIND = shutil.ignore_patterns(".venv", "tape*", "ledger.jsonl", "uv.lock", "__pycache__", ".env")
"""What a copy of a project leaves behind: what a render, uv or Python wrote in it, and the .env that holds a
developer's API keys."""


def copy_of(fixture: str, to: Path) -> Path:
    return Path(shutil.copytree(FIXTURES / fixture, to / fixture, ignore=LEFT_BEHIND))


def contrail_copy(folder: Path) -> Path:
    return Path(shutil.copytree(CONTRAIL, folder, dirs_exist_ok=True, ignore=LEFT_BEHIND))


def videotape(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the installed videotape command in a project, the way a developer does. Its requests go to a proxy that
    answers none, so a command run in examples/contrail pays nothing with the API keys a developer keeps in its .env."""
    return subprocess.run([str(VIDEOTAPE), *arguments], cwd=directory, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
                               "BROWSER": "true", "https_proxy": "http://127.0.0.1:9"})


VARIES = re.compile(r"(?P<shot>(?<=^error VT\d{3} ).+?(?= take \d|: ))|(?P<ffmpeg>(?<=decode to one frame: ).+$)"
                    r"|(?P<story>(?<=--story )\S+)|(?P<path>\S*/\S*)|(?P<hash>\b[0-9a-f]{12,64}\b)"
                    r"|(?P<number>(?<![\w.])\d+(?:\.\d+)?)", re.MULTILINE)
WILDCARDS = {"shot": r"(?:(?! take \d).)+", "ffmpeg": r".+", "story": r"\S+", "path": r"\S+", "hash": r"[0-9a-f]{12,64}",
             "number": r"\d+(?:\.\d+)?"}


def as_explained(code: str) -> re.Pattern[str]:
    """The lines a command prints for a code, as videotape explain shows them in its example and its next step or fix,
    with what differs from run to run left open: the shot, a path and the hash in it, a hash, a number, the story a
    command names, and what ffmpeg said."""
    entry = CODES[code]
    example = f"{entry.example}\n{entry.fix}"
    pattern, at = "", 0
    for part in VARIES.finditer(example):
        pattern += re.escape(example[at:part.start()]) + WILDCARDS[part.lastgroup or ""]
        at = part.end()
    return re.compile(f"^{pattern}{re.escape(example[at:])}$", re.MULTILINE)


@pytest.fixture(autouse=True, scope="session")
def refuse_urlopen():
    """No test opens a URL in this process, so none pays fal or Claude with an API key the environment or a .env
    holds."""
    def refuse(request, *args, **kwargs):
        raise AssertionError(f"a test reached for the network: {getattr(request, 'full_url', request)}")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(urllib.request, "urlopen", refuse)
        yield


@pytest.fixture(autouse=True)
def environment():
    """Drop what a project's .env added to the environment, so its keys stay in the test that loaded them. A .env
    never overrides a key, so dropping the added keys undoes it."""
    before = set(os.environ)
    yield
    for key in set(os.environ) - before:
        del os.environ[key]


@pytest.fixture
def cli(monkeypatch):
    """Run videotape's main in a project, in this process, so a test can swap the model it renders with. The project
    is forgotten before and after, so it never stands in for another project with a package of the same name."""
    def forget_any(directory: Path) -> None:
        try:
            forget(project.find(directory))
        except ScreenplayError:
            pass  # A project that is not one has no modules to forget, and the command reports it.

    def run(directory: Path, *arguments: str) -> int:
        monkeypatch.chdir(directory)
        forget_any(directory)
        try:
            return main(list(arguments))
        finally:
            forget_any(directory)
    return run
