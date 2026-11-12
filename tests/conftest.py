import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from videotape import project
from videotape.cli import main
from videotape.plan import Plan, plan

FIXTURES = Path(__file__).parent / "fixtures"
CONTRAIL = Path(__file__).parent.parent / "examples" / "contrail"
VIDEOTAPE = Path(sys.executable).with_name("videotape")

# A test edits a screenplay and loads it again within a second, which a cached .pyc would hide.
sys.dont_write_bytecode = True


def forget(found: project.Project) -> None:
    """Drop a project's modules, so a copy or an edit of the project is imported afresh."""
    top = found.screenplay.partition(":")[0].partition(".")[0]
    for name in [name for name in sys.modules if name == top or name.startswith(f"{top}.")]:
        del sys.modules[name]


def planned(directory: Path) -> Plan:
    found = project.find(directory)
    forget(found)
    return plan(found.load(), found.max_states)


def copy_of(fixture: str, to: Path) -> Path:
    """A fresh copy of a fixture project, without anything a render left in it."""
    return Path(shutil.copytree(FIXTURES / fixture, to / fixture,
                                ignore=shutil.ignore_patterns("tape*", "ledger.jsonl", "__pycache__")))


def videotape(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the installed videotape command in a project, the way a developer does."""
    return subprocess.run([str(VIDEOTAPE), *arguments], cwd=directory, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1"})


@pytest.fixture
def cli(monkeypatch):
    """Run videotape's main in a project, in this process, so a test can swap the model it renders with."""
    def run(directory: Path, *arguments: str) -> int:
        monkeypatch.chdir(directory)
        forget(project.find(directory))
        return main(list(arguments))
    return run
