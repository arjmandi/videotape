"""play builds TapePlayer when it needs to and opens the tape in it. Nothing here opens a window: the launcher is a
list that records what would run."""

import os
import time
from pathlib import Path

import pytest

from conftest import copy_of
from videotape import player
from videotape.project import ProjectError


def a_checkout(root: Path) -> Path:
    """A clients/macos as the checkout has it: the sources, the build script, and what a build leaves."""
    macos = root / "clients" / "macos"
    for path in ("build.sh", "TapeKit/Package.swift", "TapeKit/Sources/TapeKit/Tape.swift", "TapePlayer/main.swift",
                 "TapePlayer.xcodeproj/project.pbxproj", "TapeKit/.build/debug/junk", "TapePlayer.xcodeproj/xcuserdata/me",
                 ".DS_Store"):
        (macos / path).parent.mkdir(parents=True, exist_ok=True)
        (macos / path).write_text(path)
    (macos / "build.sh").chmod(0o755)
    return macos


def built(macos: Path, when: float) -> Path:
    app = macos / "build" / "TapePlayer.app"
    (app / "Contents").mkdir(parents=True, exist_ok=True)
    os.utime(app, (when, when))
    return app


def test_the_sources_are_everything_under_clients_macos_but_what_a_build_leaves(tmp_path):
    macos = a_checkout(tmp_path)
    assert sorted(path.relative_to(macos).as_posix() for path in player.sources(macos)) == [
        "TapeKit/Package.swift", "TapeKit/Sources/TapeKit/Tape.swift", "TapePlayer.xcodeproj/project.pbxproj",
        "TapePlayer/main.swift", "build.sh"]
    assert sorted(path.relative_to(player.MACOS).as_posix() for path in player.sources())[:2] == [
        "TapeKit/Package.swift", "TapeKit/Sources/TapeKit/Player.swift"]


def test_play_builds_when_the_app_is_missing_or_older_than_a_source_and_then_opens_the_tape(tmp_path):
    macos = a_checkout(tmp_path)
    tape = copy_of("cafe", tmp_path) / "tapes" / "chalk"
    tape.mkdir(parents=True)
    ran = []
    build, open_ = [str(macos / "build.sh")], ["open", str(macos / "build" / "TapePlayer.app"), "--args", str(tape.resolve())]
    assert player.play(tape, macos, ran.append) == [build, open_] and ran == [build, open_]
    now = time.time()
    app = built(macos, now)
    for path in player.sources(macos):
        os.utime(path, (now - 60, now - 60))
    ran.clear()
    assert player.play(tape, macos, ran.append) == [open_] and ran == [open_]
    os.utime(macos / "TapePlayer" / "main.swift", (now + 60, now + 60))
    assert player.commands(tape, macos) == [build, open_]
    os.utime(app, (now + 120, now + 120))
    assert player.commands(tape, macos) == [open_]
    os.utime(macos / "TapeKit" / ".build" / "debug" / "junk", (now + 600, now + 600))
    assert player.commands(tape, macos) == [open_]


def test_play_without_the_source_beside_videotape_says_so(tmp_path):
    with pytest.raises(ProjectError, match="TapePlayer's source is not at"):
        player.commands(tmp_path, tmp_path / "nowhere")


def test_play_command_needs_a_rendered_tape_and_prints_what_it_runs(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "play", "--story", "chalk") == 1
    assert capsys.readouterr().err == "error: no dailies.json in tapes/chalk; render the story first\n".replace(
        "dailies.json", "tape.json")
    tape = directory / "tapes" / "chalk"
    tape.mkdir(parents=True)
    (tape / "tape.json").write_text("{}")
    macos = a_checkout(tmp_path)
    ran = []
    monkeypatch.setattr(player, "MACOS", macos)
    monkeypatch.setattr(player, "_run", ran.append)
    assert cli(directory, "play", "--story", "chalk") == 0
    assert ran == [[str(macos / "build.sh")], ["open", str(macos / "build" / "TapePlayer.app"), "--args", str(tape.resolve())]]
    assert capsys.readouterr().out == f"{macos / 'build.sh'}\nopen {macos / 'build' / 'TapePlayer.app'} --args {tape.resolve()}\n"
