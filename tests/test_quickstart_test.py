"""How scripts/quickstart-test judges a step from what it printed. Running the quickstart itself takes minutes and the
screen, so it is run by hand."""

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
DOCTOR = "uv run videotape doctor"


@pytest.fixture(scope="module")
def script():
    loader = importlib.machinery.SourceFileLoader("quickstart_test", str(ROOT / "scripts" / "quickstart-test"))
    spec = importlib.util.spec_from_loader("quickstart_test", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


EXTRA = ("fail VT105 wan3.0's checks run Qwen3-VL-8B through videotape's qwen extra, which is not installed here\n"
         "  fix: in pyproject.toml, put [qwen] right after videotape in dependencies\n")


@pytest.mark.parametrize("code, said, ok", [
    (0, "ok   VT101 Python 3.14.0, and videotape needs >=3.12\nok   VT104 FAL_KEY is set, for wan3.0\n", True),
    (1, "ok   VT103 Xcode 27.0\nfail VT104 wan3.0 needs FAL_KEY\n  fix: copy .env.example to .env\n", True),
    (1, f"ok   VT103 Xcode 27.0\nfail VT104 wan3.0 needs FAL_KEY\n{EXTRA}", True),
    (1, f"ok   VT104 FAL_KEY is set, for wan3.0\n{EXTRA}", True),
    (1, "fail VT105 wan3.0's checks need Apple silicon or a CUDA GPU, and this machine is Linux on x86_64\n", False),
    (1, f"fail VT102 ffprobe is not on PATH\n  fix: install ffmpeg\n{EXTRA}", False),
    (1, "fail VT102 ffprobe is not on PATH\n  fix: install ffmpeg\nfail VT104 wan3.0 needs FAL_KEY\n", False),
    (1, "fail VT103 xcode-select is not here, so TapePlayer cannot build\n", False),
    (1, "error VT107 pyproject.toml: [tool.videotape] model is 3, not a model's name\n", False),
])
def test_doctor_passes_with_no_fail_but_the_key_and_the_extra_the_starters_model_needs(script, code, said, ok):
    assert script.passed(script.Ran(DOCTOR, 1.0, code, said)) is ok


def test_another_step_passes_only_when_it_exits_0(script):
    assert script.passed(script.Ran(script.PLAY, 1.0, 0, ""))
    assert not script.passed(script.Ran(script.PLAY, 1.0, 1, "fail VT104 wan3.0 needs FAL_KEY\n"))


def test_tapeplayers_first_build_is_read_from_plays_line_and_a_cached_player_built_nothing(script):
    said = "building TapePlayer, once for this version of it\nbuilt TapePlayer in 41.7 s\nopen /c/TapePlayer.app --args /t\n"
    assert script.first_build(script.Ran(script.PLAY, 44.0, 0, said)) == 41.7
    assert script.first_build(script.Ran(script.PLAY, 1.0, 0, "open /c/TapePlayer.app --args /t\n")) == 0.0


def test_the_steps_to_a_played_tape_are_within_the_budget(script):
    assert script.STEPS[:script.TO_A_PLAYED_TAPE] == [
        "uvx --from {repo} videotape new contrail", "cd contrail", DOCTOR,
        "uv run videotape render --story starter --model stand-in", script.PLAY]
    assert script.TO_A_PLAYED_TAPE <= script.MOST_STEPS
    assert script.STEPS[script.TO_A_PLAYED_TAPE:] == ["uv run videotape publish --story starter"]
