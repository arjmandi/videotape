"""doctor checks the machine and, in a project, each key its model and its model's readers need and what its eye
needs. The machine here is made up: a PATH of scripts that answer as ffmpeg, ffprobe, xcode-select and xcodebuild do, a
platform said to be Apple silicon, and the qwen extra said to be installed."""

import platform
import sys
from pathlib import Path

import pytest

from conftest import copy_of
from videotape import qwen
from videotape.errors import CODES

XCODE = "/Applications/Xcode.app/Contents/Developer"
PYTHON = f"Python {'.'.join(map(str, sys.version_info[:3]))}, and videotape needs >=3.12"
FINE = [f"ok   VT101 {PYTHON}", "ok   VT102 ffmpeg and ffprobe are on PATH",
        f"ok   VT103 Xcode 27.0, at {XCODE}, for TapePlayer"]
KEYS = ["ok   VT104 FAL_KEY is set, for wan3.0", "ok   VT104 ANTHROPIC_API_KEY is set, for wan3.0's reader claude-opus-5-5"]
NO_READER_KEY = ["fail VT104 wan3.0's reader claude-opus-5-5 needs ANTHROPIC_API_KEY, and it is not in the environment or "
                 ".env", "  fix: copy .env.example to .env and set ANTHROPIC_API_KEY there, or export it"]
EXTRA = "ok   VT105 Apple silicon and videotape's qwen extra, for wan3.0's checks"
INSTALLED = qwen.installed


def tool(bin: Path, name: str, says: str = "", exits: int = 0) -> None:
    (bin / name).write_text(f"#!/bin/sh\nprintf '%s' '{says}'\nexit {exits}\n")
    (bin / name).chmod(0o755)


@pytest.fixture
def machine(tmp_path, monkeypatch) -> Path:
    """Apple silicon with ffmpeg, ffprobe, Xcode and the qwen extra, and no FAL_KEY. A test takes away what it
    checks."""
    bin = tmp_path / "bin"
    bin.mkdir()
    for name in ("ffmpeg", "ffprobe"):
        tool(bin, name)
    tool(bin, "xcode-select", f"{XCODE}\n")
    tool(bin, "xcodebuild", "Xcode 27.0\nBuild version 27A266a\n")
    monkeypatch.setenv("PATH", str(bin))
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    monkeypatch.setattr(qwen, "installed", lambda: True)
    return bin


def on_wan3(tmp_path: Path, key: bool = True) -> Path:
    """The cafe, set to render with wan3.0, with its keys in .env or without them."""
    directory = copy_of("cafe", tmp_path)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('model = "stand-in"', 'model = "wan3.0"'))
    if key:
        (directory / ".env").write_text("FAL_KEY=fal-not-a-real-key\nANTHROPIC_API_KEY=sk-ant-not-a-real-key\n")
    return directory


def test_in_a_project_on_a_machine_with_everything_every_check_is_ok(tmp_path, cli, capsys, machine):
    assert cli(on_wan3(tmp_path), "doctor") == 0
    assert capsys.readouterr() == ("\n".join([*FINE, *KEYS, EXTRA]) + "\n", "")


def test_outside_a_project_doctor_checks_the_machine_only(tmp_path, cli, capsys, machine):
    (tmp_path / "empty").mkdir()
    assert cli(tmp_path / "empty", "doctor") == 0
    assert capsys.readouterr() == ("\n".join(FINE) + "\n", "")


def test_the_stand_in_needs_no_key_and_no_gpu(tmp_path, cli, capsys, machine, monkeypatch):
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    assert cli(copy_of("cafe", tmp_path), "doctor") == 0
    assert capsys.readouterr().out.splitlines()[3:] == ["ok   VT104 stand-in needs no API key",
                                                        "ok   VT105 stand-in's checks need no GPU"]


def test_an_older_python_fails_vt101(tmp_path, cli, capsys, machine, monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 11, 4, "final", 0))
    assert cli(on_wan3(tmp_path), "doctor") == 1
    assert capsys.readouterr().out.splitlines()[:2] == [
        CODES["VT101"].example,
        "  fix: make the project's environment with a newer Python, as in uv sync --python 3.12"]


@pytest.mark.parametrize("missing, line", [(["ffprobe"], "ffprobe is not on PATH"),
                                           (["ffmpeg", "ffprobe"], "ffmpeg and ffprobe are not on PATH")])
def test_ffmpeg_or_ffprobe_off_path_fails_vt102(tmp_path, cli, capsys, machine, missing, line):
    for name in missing:
        (machine / name).unlink()
    assert cli(on_wan3(tmp_path), "doctor") == 1
    assert capsys.readouterr().out.splitlines()[1:3] == [
        f"fail VT102 {line}", "  fix: install ffmpeg, which brings ffprobe, as in brew install ffmpeg"]
    if missing == ["ffprobe"]:
        assert f"fail VT102 {line}" == CODES["VT102"].example


@pytest.mark.parametrize("select, build, line", [
    ("/Library/Developer/CommandLineTools", 1, "xcode-select points at /Library/Developer/CommandLineTools, the Command "
     "Line Tools without Xcode"),
    (XCODE, 1, "xcodebuild does not run"),
    (None, None, "xcode-select is not here"),
])
def test_no_xcode_fails_vt103(tmp_path, cli, capsys, machine, select, build, line):
    if select is None:
        (machine / "xcode-select").unlink()
        (machine / "xcodebuild").unlink()
    else:
        tool(machine, "xcode-select", f"{select}\n")
        tool(machine, "xcodebuild", "xcode-select: error: tool 'xcodebuild' requires Xcode\n", exits=build)
    assert cli(on_wan3(tmp_path), "doctor") == 1
    assert capsys.readouterr().out.splitlines()[2:4] == [
        f"fail VT103 {line}, so TapePlayer cannot build",
        "  fix: install Xcode from the App Store, then point xcode-select at it, as in "
        "sudo xcode-select --switch /Applications/Xcode.app"]
    if select == "/Library/Developer/CommandLineTools":
        assert f"fail VT103 {line}, so TapePlayer cannot build" == CODES["VT103"].example


def test_a_key_in_neither_the_environment_nor_env_fails_vt104_and_a_blank_one_is_not_a_key(tmp_path, cli, capsys,
                                                                                          machine):
    directory = on_wan3(tmp_path, key=False)
    (directory / ".env").write_text("FAL_KEY=\n")
    assert cli(directory, "doctor") == 1
    assert capsys.readouterr().out.splitlines()[3:] == [
        CODES["VT104"].example,
        "  fix: copy .env.example to .env and set FAL_KEY there, or export it", *NO_READER_KEY, EXTRA]


def test_a_key_with_a_line_break_fails_vt104_as_a_render_with_it_would(tmp_path, cli, capsys, machine, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "fal-not-a\nreal-key")
    assert cli(on_wan3(tmp_path, key=False), "doctor") == 1
    assert capsys.readouterr().out.splitlines()[3:5] == [
        "fail VT104 FAL_KEY holds a character an HTTP header cannot carry, such as a line break",
        "  fix: set FAL_KEY to the API key alone, in .env or the environment"]


def test_a_key_in_the_environment_is_enough(tmp_path, cli, capsys, machine, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "fal-not-a-real-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    assert cli(on_wan3(tmp_path, key=False), "doctor") == 0
    said = "".join(capsys.readouterr())
    assert "fal-not-a-real-key" not in said and "sk-ant-not-a-real-key" not in said


def test_each_reader_that_runs_as_a_service_needs_its_own_key(tmp_path, cli, capsys, machine):
    directory = on_wan3(tmp_path, key=False)
    (directory / ".env").write_text("FAL_KEY=fal-not-a-real-key\n")
    assert cli(directory, "doctor") == 1
    assert capsys.readouterr().out.splitlines()[3:] == [KEYS[0], *NO_READER_KEY, EXTRA]


def test_a_wan_model_without_apple_silicon_or_cuda_fails_vt105_and_with_cuda_passes(tmp_path, cli, capsys, machine,
                                                                                    monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    directory = on_wan3(tmp_path)
    assert cli(directory, "doctor") == 1
    assert capsys.readouterr().out.splitlines()[5:] == [
        "fail VT105 wan3.0's checks need Apple silicon or a CUDA GPU, and this machine is Linux on x86_64 without "
        "nvidia-smi",
        "  fix: render on a Mac with Apple silicon or a machine with a CUDA GPU, or with the stand-in, as in "
        "videotape render --story starter --model stand-in"]
    tool(machine, "nvidia-smi")
    assert cli(directory, "doctor") == 0
    assert capsys.readouterr().out.splitlines()[5] == "ok   VT105 a CUDA GPU and videotape's qwen extra, for wan3.0's checks"


def without(monkeypatch, missing: str) -> None:
    """Every distribution installed but the one named missing, as videotape's metadata reads them."""
    def distribution(name: str):
        if name == missing:
            raise qwen.PackageNotFoundError(name)
        return None
    monkeypatch.setattr(qwen, "installed", INSTALLED)
    monkeypatch.setattr(qwen, "distribution", distribution)


@pytest.mark.parametrize("missing", ["torch", "accelerate"])
def test_a_wan_model_without_the_qwen_extra_fails_vt105_and_says_to_add_it_to_the_videotape_dependency(
        missing, tmp_path, cli, capsys, machine, monkeypatch):
    without(monkeypatch, missing)
    assert cli(on_wan3(tmp_path), "doctor") == 1
    assert capsys.readouterr().out.splitlines()[3:] == [*KEYS, CODES["VT105"].example, f"  fix: {CODES['VT105'].fix}"]
    assert CODES["VT105"].fix == (
        'in pyproject.toml, put [qwen] right after videotape in dependencies, as in "videotape[qwen] @ '
        'file:///Users/me/videotape-p1p" or "videotape[qwen]==0.1.0", then run uv sync')


def test_the_qwen_extra_counts_as_installed_when_every_distribution_it_names_is(monkeypatch):
    without(monkeypatch, "none of them")
    assert qwen.installed()


def test_a_project_with_a_wrong_value_fails_its_vt107_after_the_machine(tmp_path, cli, capsys, machine):
    directory = on_wan3(tmp_path)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('"wan3.0"', '"wan3"'))
    assert cli(directory, "doctor") == 1
    assert capsys.readouterr().out.splitlines()[3:] == [
        'fail VT107 pyproject.toml: [tool.videotape] model is "wan3", and videotape has no such model',
        "  fix: set model to one of gemini-omni-flash-1.2, minimax-h3, stand-in, wan2.2-5b, wan3.0"]
