"""play builds TapePlayer into a cache once per version of its source and opens the tape in it. Nothing here runs
xcodebuild or opens a window: the build is a stand-in that leaves an app, and the launcher records what would run."""

import subprocess
from pathlib import Path

import pytest

from conftest import copy_of
from videotape import player
from videotape.errors import ScreenplayError

MACOS = Path(__file__).parent.parent / "clients" / "macos"


def a_source(root: Path) -> Path:
    """A TapePlayer source as the checkout has it: what a build reads, its tests, and what a build or Xcode leaves."""
    macos = root / "macos"
    for path in ("build.sh", "test.sh", "TapeKit/Package.swift", "TapeKit/Sources/TapeKit/Tape.swift",
                 "TapeKit/Tests/TapeKitTests/LoadTests.swift", "TapePlayer/main.swift", "TapePlayerUITests/Walk.swift",
                 "TapePlayer.xcodeproj/project.pbxproj", "TapeKit/.build/debug/junk", "TapePlayer.xcodeproj/xcuserdata/me",
                 "build/TapePlayer.app/Contents/Info.plist", ".DS_Store"):
        (macos / path).parent.mkdir(parents=True, exist_ok=True)
        (macos / path).write_text(path)
    return macos


class Builds:
    """A build that leaves an app, or fails the way xcodebuild does without Xcode, and records what it was given."""

    def __init__(self, fails: bool = False):
        self.fails, self.given = fails, []

    def __call__(self, folder: Path) -> subprocess.CompletedProcess[str]:
        self.given.append(sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()))
        if self.fails:
            return subprocess.CompletedProcess([], 1, "", "xcode-select: error: tool 'xcodebuild' requires Xcode\n"
                                               "** BUILD FAILED **\n")
        (folder / "build" / "TapePlayer.app" / "Contents").mkdir(parents=True)
        (folder / "build" / "TapePlayer.app" / "Contents" / "Info.plist").write_text("built")
        return subprocess.CompletedProcess([], 0, "built\n", "")


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOTAPE_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path / "cache"


def test_the_source_in_a_checkout_is_clients_macos_and_holds_only_what_a_build_reads(tmp_path):
    assert player.SOURCE == MACOS
    macos = a_source(tmp_path)
    assert sorted(path.relative_to(macos).as_posix() for path in player.sources(macos)) == [
        "TapeKit/Package.swift", "TapeKit/Sources/TapeKit/Tape.swift", "TapePlayer.xcodeproj/project.pbxproj",
        "TapePlayer/main.swift", "build.sh"]


def test_tapeplayer_builds_once_per_version_of_its_source_into_the_cache(tmp_path, cache, monkeypatch, capsys):
    macos, build = a_source(tmp_path), Builds()
    monkeypatch.setattr(player, "_build", build)
    app = player.built(macos)
    assert app.parent.parent == cache / "player" and app.name == "TapePlayer.app"
    assert (app / "Contents" / "Info.plist").read_text() == "built"
    assert build.given == [["TapeKit/Package.swift", "TapeKit/Sources/TapeKit/Tape.swift",
                            "TapePlayer.xcodeproj/project.pbxproj", "TapePlayer/main.swift", "build.sh"]]
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "building TapePlayer, once for this version of it"
    assert out[1].startswith("built TapePlayer in ") and out[1].endswith(" s") and len(out) == 2
    assert [path.name for path in app.parent.iterdir()] == ["TapePlayer.app"]

    assert player.built(macos) == app and len(build.given) == 1 and capsys.readouterr().out == ""
    (macos / "TapeKit" / "Tests" / "TapeKitTests" / "LoadTests.swift").write_text("a test changed")
    (macos / "TapeKit" / ".build" / "debug" / "junk").write_text("a build left more")
    assert player.built(macos) == app and len(build.given) == 1

    (macos / "TapePlayer" / "main.swift").write_text("the app changed")
    again = player.built(macos)
    assert again != app and again.parent.parent == cache / "player" and len(build.given) == 2


def test_a_build_that_fails_is_vt603_naming_its_log_and_caches_nothing(tmp_path, cache, monkeypatch):
    macos = a_source(tmp_path)
    monkeypatch.setattr(player, "_build", Builds(fails=True))
    with pytest.raises(ScreenplayError) as raised:
        player.built(macos)
    log = Path(raised.value.place)
    assert raised.value.code == "VT603" and log.name == "build.log"
    assert raised.value.message == "the build exited with 1: xcode-select: error: tool 'xcodebuild' requires Xcode"
    assert raised.value.fix.startswith("run videotape doctor")
    assert log.read_text() == "xcode-select: error: tool 'xcodebuild' requires Xcode\n** BUILD FAILED **\n"
    assert [path.name for path in log.parent.iterdir()] == ["build.log"]
    monkeypatch.setattr(player, "_build", Builds())
    assert player.built(macos).is_dir()
    assert [path.name for path in log.parent.iterdir()] == ["TapePlayer.app"]


def test_a_source_without_its_build_script_is_vt603(tmp_path, cache):
    with pytest.raises(ScreenplayError, match="TapePlayer's source is not here") as raised:
        player.built(tmp_path / "nowhere")
    assert raised.value.code == "VT603"


def test_play_needs_a_rendered_tape_then_builds_the_player_and_opens_the_tape(tmp_path, cli, cache, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "play", "--story", "chalk") == 1
    assert capsys.readouterr().err == "error: no tape.json in tapes/chalk; render the story first\n"
    tape = directory / "tapes" / "chalk"
    tape.mkdir(parents=True)
    (tape / "tape.json").write_text("{}")
    build, opened = Builds(), []
    monkeypatch.setattr(player, "_build", build)
    monkeypatch.setattr(player, "_launch", opened.append)
    assert cli(directory, "play", "--story", "chalk") == 0
    [app] = (cache / "player").glob("*/TapePlayer.app")
    assert opened == [["open", str(app), "--args", str(tape.resolve())]]
    assert "TapePlayerUITests/TapePlayerUITests.swift" not in build.given[0] and "build.sh" in build.given[0]
    out = capsys.readouterr().out.splitlines()
    assert out[1].startswith("built TapePlayer in ") and out[2] == f"open {app} --args {tape.resolve()}"
    assert cli(directory, "play", "--story", "chalk") == 0
    assert len(build.given) == 1 and capsys.readouterr().out == f"open {app} --args {tape.resolve()}\n"


def test_play_says_when_the_player_did_not_build(tmp_path, cli, cache, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    (directory / "tapes" / "chalk").mkdir(parents=True)
    (directory / "tapes" / "chalk" / "tape.json").write_text("{}")
    monkeypatch.setattr(player, "_build", Builds(fails=True))
    assert cli(directory, "play", "--story", "chalk") == 1
    out, err = capsys.readouterr()
    log = cache / "player" / next((cache / "player").iterdir()).name / "build.log"
    assert out == "building TapePlayer, once for this version of it\n"
    assert err == (f"error VT603 {log}: the build exited with 1: xcode-select: error: tool 'xcodebuild' requires Xcode\n"
                   "fix: run videotape doctor, which looks for Xcode; when it finds Xcode, the log says what failed\n")
