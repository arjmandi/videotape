import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import BROKEN, SAMPLES, load_sample

from videotape.check import RULES
from videotape.spec import intent_schema

EXE = shutil.which("videotape", path=str(Path(sys.executable).parent))


def videotape(*args, cwd=None):
    return subprocess.run([EXE, *args], cwd=cwd, capture_output=True, text=True)


def test_the_console_script_is_installed():
    assert EXE is not None


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_intent_prints_the_intent(name):
    directory, module = SAMPLES[name]
    run = videotape("intent", f"{module}:app", "--app-dir", str(directory))
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == load_sample(name).app.intent()


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_check_passes_the_samples(name):
    directory, module = SAMPLES[name]
    run = videotape("check", module, "--app-dir", str(directory))
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.strip().endswith("no problems")


def test_the_module_is_found_in_the_current_directory():
    directory, module = SAMPLES["hello"]
    assert videotape("check", f"{module}:app", cwd=directory).returncode == 0


@pytest.mark.parametrize("code", sorted(RULES))
def test_check_exits_1_on_errors_and_0_on_warnings(code):
    run = videotape("check", code.replace("-", "_"), "--app-dir", str(BROKEN))
    level, _ = RULES[code]
    assert run.returncode == (1 if level == "error" else 0)
    assert f"[{code}]" in run.stdout


def test_check_prints_json():
    run = videotape("check", "unknown_tape", "--app-dir", str(BROKEN), "--json")
    assert run.returncode == 1
    diagnostics = json.loads(run.stdout)
    assert [d["code"] for d in diagnostics] == ["unknown-tape", "unknown-tape"]
    assert diagnostics[0] == {
        "level": "error", "code": "unknown-tape", "at": "home/write-a-note",
        "message": "save() returns vt.jump('notes'), but there is no tape 'notes'"}  # fmt: skip


def test_intent_fails_on_an_unreadable_record():
    run = videotape("intent", "unreadable_record", "--app-dir", str(BROKEN))
    assert run.returncode == 1 and "Line" in run.stderr


def test_schema_prints_the_published_schema():
    run = videotape("schema")
    assert run.returncode == 0 and json.loads(run.stdout) == intent_schema()


@pytest.mark.parametrize("target", ["nowhere:app", "conftest:app", ":app"])
def test_bad_targets_exit_2(target):
    run = videotape("check", target, "--app-dir", str(Path(__file__).parent))
    assert run.returncode == 2 and run.stderr.startswith("videotape:")
