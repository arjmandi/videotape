"""doctor checks the machine and, in a project, its model's key and GPU. The machine here is made up: a PATH of
scripts that answer as ffmpeg, ffprobe, xcode-select and xcodebuild do, and a platform said to be Apple silicon."""

import platform
import sys
from pathlib import Path

import pytest

from conftest import copy_of
from videotape.errors import CODES

XCODE = "/Applications/Xcode.app/Contents/Developer"
PYTHON = f"Python {'.'.join(map(str, sys.version_info[:3]))}, and videotape needs >=3.12"
FINE = [f"ok   VT101 {PYTHON}", "ok   VT102 ffmpeg and ffprobe are on PATH",
        f"ok   VT103 Xcode 27.0, at {XCODE}, for TapePlayer"]


def tool(bin: Path, name: str, says: str = "", exits: int = 0) -> None:
    (bin / name).write_text(f"#!/bin/sh\nprintf '%s' '{says}'\nexit {exits}\n")
    (bin / name).chmod(0o755)


@pytest.fixture
def machine(tmp_path, monkeypatch) -> Path:
    """Apple silicon with ffmpeg, ffprobe and Xcode, and no FAL_KEY. A test takes away what it checks."""
    bin = tmp_path / "bin"
    bin.mkdir()
    for name in ("ffmpeg", "ffprobe"):
        tool(bin, name)
    tool(bin, "xcode-select", f"{XCODE}\n")
    tool(bin, "xcodebuild", "Xcode 27.0\nBuild version 27A266a\n")
    monkeypatch.setenv("PATH", str(bin))
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    return bin


def on_wan3(tmp_path: Path, key: bool = True) -> Path:
    """The cafe, set to render with wan3.0, with its key in .env or without one."""
    directory = copy_of("cafe", tmp_path)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('model = "stand-in"', 'model = "wan3.0"'))
    if key:
        (directory / ".env").write_text("FAL_KEY=fal-not-a-real-key\n")
    return directory


def test_in_a_project_on_a_machine_with_everything_every_check_is_ok(tmp_path, cli, capsys, machine):
    assert cli(on_wan3(tmp_path), "doctor") == 0
    assert capsys.readouterr() == ("\n".join([*FINE, "ok   VT104 FAL_KEY is set, for wan3.0",
                                              "ok   VT105 Apple silicon, for wan3.0's checks"]) + "\n", "")


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
        "  fix: copy .env.example to .env and set FAL_KEY there, or export it",
        "ok   VT105 Apple silicon, for wan3.0's checks"]


def test_a_key_in_the_environment_is_enough(tmp_path, cli, capsys, machine, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "fal-not-a-real-key")
    assert cli(on_wan3(tmp_path, key=False), "doctor") == 0
    assert "fal-not-a-real-key" not in "".join(capsys.readouterr())


def test_a_wan_model_without_apple_silicon_or_cuda_fails_vt105_and_with_cuda_passes(tmp_path, cli, capsys, machine,
                                                                                    monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    directory = on_wan3(tmp_path)
    assert cli(directory, "doctor") == 1
    assert capsys.readouterr().out.splitlines()[4:] == [
        CODES["VT105"].example,
        "  fix: render on a Mac with Apple silicon or a machine with a CUDA GPU, or with the stand-in, as in "
        "videotape render --story starter --model stand-in"]
    tool(machine, "nvidia-smi")
    assert cli(directory, "doctor") == 0
    assert capsys.readouterr().out.splitlines()[4] == "ok   VT105 a CUDA GPU, for wan3.0's checks"


def test_a_project_with_a_wrong_value_fails_its_vt107_after_the_machine(tmp_path, cli, capsys, machine):
    directory = on_wan3(tmp_path)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('"wan3.0"', '"wan3"'))
    assert cli(directory, "doctor") == 1
    assert capsys.readouterr().out.splitlines()[3:] == [
        'fail VT107 pyproject.toml: [tool.videotape] model is "wan3", and videotape has no such model',
        "  fix: set model to one of stand-in, wan2.2-5b, wan3.0"]
