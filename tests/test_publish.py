"""videotape publish makes a rendered tape into a Mac app in dist/: TapePlayer named for the app and the story, with
the tape inside it, each clip encoded as HEVC, signed ad hoc and zipped, and recorded in videotape.lock. It refuses a
tape out of date with its sources, failing checks nobody accepted, a label the lock holds with another id, a player
that does not build, and an encoded clip whose last frame fails a check its key passed. The player built here is an
app bundle around /usr/bin/true, so codesign has a real executable to sign and nothing runs xcodebuild or a window."""

import contextlib
import dataclasses
import hashlib
import itertools
import json
import plistlib
import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path

import pytest

from conftest import as_explained, forget, told
from videotape import doctor, frames, made, new, player, project, publish
from videotape.cli import main
from videotape.errors import CODES
from videotape.model import MODELS, Listing
from videotape.checks import Spot
from videotape.standin import Flaw, StandIn, StandInEye
from videotape.plan import Mode
from videotape.hosted import WAN3

LABEL = "contrail 0.1.0 + starter 1.0.0"


def tapeplayer(folder: Path) -> subprocess.CompletedProcess[str]:
    """A build that leaves an app codesign can sign: TapePlayer's Info.plist over a copy of /usr/bin/true."""
    contents = folder / "build" / "TapePlayer.app" / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    shutil.copy(Path("/usr/bin/true"), contents / "MacOS" / "TapePlayer")
    (contents / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleExecutable": "TapePlayer", "CFBundleIdentifier": "dev.videotape.TapePlayer", "CFBundleName": "TapePlayer",
        "CFBundlePackageType": "APPL", "NSPrincipalClass": "NSApplication"}))
    return subprocess.CompletedProcess([], 0, "built\n", "")


@pytest.fixture(scope="module")
def starter(tmp_path_factory) -> Path:
    """The project videotape new contrail writes, rendered with the stand-in."""
    folder = new.project("contrail", tmp_path_factory.mktemp("starter"))
    found = project.find(folder)
    forget(found)
    try:
        with contextlib.chdir(folder):
            assert main(["render", "--story", "starter", "--model", "stand-in"]) == 0
    finally:
        forget(found)
    return folder


@pytest.fixture
def contrail(starter, tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("VIDEOTAPE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(player, "_build", tapeplayer)
    monkeypatch.delenv("FAL_KEY", raising=False)
    return Path(shutil.copytree(starter, tmp_path / "contrail"))


def manifest(folder: Path) -> dict:
    return json.loads((folder / "tapes" / "starter" / "tape.json").read_text())


def probe(clip: Path) -> list[str]:
    """A clip's codec, its tag and its frame count."""
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                           "stream=codec_name,codec_tag_string,nb_read_frames", "-of", "csv=p=0", str(clip)],
                          capture_output=True, text=True, check=True).stdout.strip().split(",")


def signed(app: Path) -> bool:
    return subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], capture_output=True).returncode == 0


def megabytes(size: int) -> str:
    return f"{size / 1e6:.1f} MB"


def test_publish_makes_the_starter_into_a_signed_app_that_holds_its_tape_and_records_it(contrail, cli, capsys, tmp_path):
    assert cli(contrail, "publish", "--story", "starter") == 0
    out, err = capsys.readouterr()
    app, zipped, made_by = contrail / "dist" / "Contrail-starter.app", contrail / "dist" / "Contrail-starter.zip", manifest(contrail)["made"]
    size = sum(path.stat().st_size for path in app.rglob("*") if path.is_file())
    assert err == ""
    lines = out.splitlines()
    assert lines[0] == "building TapePlayer, once for this version of it" and lines[1].startswith("built TapePlayer in ")
    assert lines[2:] == [
        "encoded 3 clips as HEVC; on each one's last frame, where TapePlayer rests, every check its key passed still "
        "passes",
        "signed ad hoc, not with a Developer ID, so another Mac's Gatekeeper asks before it opens the app",
        f"published dist/Contrail-starter.app, {megabytes(size)}, zipped to dist/Contrail-starter.zip, "
        f"{megabytes(zipped.stat().st_size)}",
        f"label {LABEL}", f"id {made_by['id']}", "videotape.lock holds the label now; commit it"]
    assert sorted(path.name for path in (contrail / "dist").iterdir()) == ["Contrail-starter.app", "Contrail-starter.zip"]

    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert {key: info[key] for key in ("CFBundleName", "CFBundleDisplayName", "CFBundleIdentifier", "CFBundleExecutable")} \
        == {"CFBundleName": "Contrail (Starter)", "CFBundleDisplayName": "Contrail (Starter)",
            "CFBundleIdentifier": "dev.videotape.contrail.starter", "CFBundleExecutable": "TapePlayer"}

    inside, tape = app / "Contents" / "Resources" / "tape", contrail / "tapes" / "starter"
    clips = [manifest(contrail)["opening"]["clip"], *(move["clip"] for move in manifest(contrail)["moves"].values())]
    assert sorted(path.relative_to(inside).as_posix() for path in inside.rglob("*") if path.is_file()) == \
        sorted(["tape.json", *clips])
    assert (inside / "tape.json").read_bytes() == (tape / "tape.json").read_bytes()
    for clip in clips:
        assert probe(inside / clip) == ["hevc", "hvc1", probe(tape / clip)[2]], clip

    assert signed(app)
    shown = subprocess.run(["codesign", "-dv", str(app)], capture_output=True, text=True).stderr.splitlines()
    assert {"Identifier=dev.videotape.contrail.starter", "Signature=adhoc"} <= set(shown)
    subprocess.run(["ditto", "-x", "-k", str(zipped), str(tmp_path / "unzipped")], check=True)
    assert [path.name for path in (tmp_path / "unzipped").iterdir()] == ["Contrail-starter.app"]
    assert signed(tmp_path / "unzipped" / "Contrail-starter.app")

    settings = hashlib.sha256(json.dumps(made_by["model"]["settings"], sort_keys=True).encode()).hexdigest()
    lock = (contrail / "videotape.lock").read_text()
    assert lock.startswith("# What videotape publish shipped")
    assert tomllib.loads(lock) == {LABEL: {
        "id": made_by["id"], "screenplay": "contrail.screenplay:app", "code": made_by["app"]["code"],
        "data": made_by["app"]["data"],
        "story": made_by["story"]["hash"], "model": "stand-in", "settings": settings, "engine": made_by["engine"]}}

    assert cli(contrail, "publish", "--story", "starter") == 0
    out, err = capsys.readouterr()
    assert err == "" and out.splitlines()[0].startswith("encoded 3 clips as HEVC")
    assert out.splitlines()[-3:] == [f"label {LABEL}", f"id {made_by['id']}", "videotape.lock held the label already"]
    assert (contrail / "videotape.lock").read_text() == lock
    assert sorted(path.name for path in (contrail / "dist").iterdir()) == ["Contrail-starter.app", "Contrail-starter.zip"]
    assert signed(app)



class Wider(StandIn):
    """Pads every key take to 1344x768 in the stand-in's background, the size minimax-h3 draws at, so the moves the
    stand-in fades between two keys are 1344x768 too."""

    def text_to_video(self, prompt, seed, out):
        drawn = out.with_name(f"drawn-{out.name}")
        super().text_to_video(prompt, seed, drawn)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(drawn), "-vf", "pad=1344:768:32:32:color=0x2f6f7e",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24", "-f", "mp4", "-y", str(out)], check=True)
        drawn.unlink()


def test_a_1344x768_tape_is_published_at_its_own_size(contrail, cli, capsys, monkeypatch):
    monkeypatch.setitem(MODELS, "stand-in", dataclasses.replace(
        MODELS["stand-in"], model=lambda: Wider(flaw=lambda mode, prompt, seed: Flaw.NONE)))
    shutil.rmtree(contrail / "tapes" / "starter")
    assert cli(contrail, "render", "--story", "starter", "--model", "stand-in") == 0
    assert manifest(contrail)["size"] == {"width": 1344, "height": 768}
    capsys.readouterr()
    assert cli(contrail, "publish", "--story", "starter") == 0
    assert capsys.readouterr().out.splitlines()[2].startswith("encoded 3 clips as HEVC; on each one's last frame")
    inside = contrail / "dist" / "Contrail-starter.app" / "Contents" / "Resources" / "tape"
    clips = [manifest(contrail)["opening"]["clip"], *(move["clip"] for move in manifest(contrail)["moves"].values())]
    assert {(probe(inside / clip)[0], frames.shape(inside / clip)) for clip in clips} == {("hevc", frames.Shape(1344, 768, 24))}
    assert json.loads((inside / "tape.json").read_text())["size"] == {"width": 1344, "height": 768}

def shipped(folder: Path) -> tuple[list[str], str | None, str | None, str | None]:
    """What a publish leaves: the names in dist/, the made id of the tape in the app and in the zip, and the lock."""
    dist, lock = folder / "dist", folder / "videotape.lock"
    in_app = dist / "Contrail-starter.app" / "Contents" / "Resources" / "tape" / "tape.json"
    in_zip = None
    if (dist / "Contrail-starter.zip").is_file():
        with zipfile.ZipFile(dist / "Contrail-starter.zip") as zipped:
            in_zip = json.loads(zipped.read("Contrail-starter.app/Contents/Resources/tape/tape.json"))["made"]["id"]
    return (sorted(path.name for path in dist.iterdir()) if dist.is_dir() else [],
            json.loads(in_app.read_text())["made"]["id"] if in_app.is_file() else None, in_zip,
            lock.read_text() if lock.is_file() else None)


def stopped(cli, folder: Path, at: int) -> bool:
    """Publish in the folder, stopped as by Ctrl-C at its at-th step that writes, counted from 0: codesign, the zip,
    and each rename or replace. False when the publish finished before that step."""
    steps = itertools.count()
    with pytest.MonkeyPatch.context() as patch:
        for owner, name in ((publish, "_run"), (Path, "rename"), (Path, "replace")):
            def step(*arguments, real=getattr(owner, name)):
                if next(steps) == at:
                    raise KeyboardInterrupt
                return real(*arguments)
            patch.setattr(owner, name, step)
        try:
            assert cli(folder, "publish", "--story", "starter") == 0
        except KeyboardInterrupt:
            return True
    return False


def test_a_publish_stopped_or_failing_at_any_step_leaves_the_old_app_zip_and_lock_whole_or_the_new_ones(
        contrail, cli, capsys, monkeypatch, tmp_path):
    """The clips are copied into the app, not encoded, which the swap does not need."""
    monkeypatch.setattr(frames, "hevc", shutil.copyfile)
    assert cli(contrail, "publish", "--story", "starter") == 0
    old = shipped(contrail)
    pyproject = contrail / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('version = "0.1.0"', 'version = "0.1.1"'))
    assert cli(contrail, "render", "--story", "starter", "--model", "stand-in") == 0
    left = []
    for at in itertools.count():
        folder = Path(shutil.copytree(contrail, tmp_path / f"stopped-at-{at}"))
        if not stopped(cli, folder, at):
            break
        left.append(shipped(folder))
    new = shipped(folder)
    assert old != new and new[1] == new[2] == manifest(contrail)["made"]["id"]
    assert len(left) >= 5 and all(state in (old, new) for state in left), left

    folder, run = Path(shutil.copytree(contrail, tmp_path / "zip-fails")), publish._run
    monkeypatch.setattr(publish, "_run", lambda *command: run(*command) if command[0] != "ditto" else
                        run("ditto", "-c", "-k", str(tmp_path / "nothing"), str(tmp_path / "nothing.zip")))
    capsys.readouterr()
    assert cli(folder, "publish", "--story", "starter") == 1
    assert capsys.readouterr().err.startswith("error VT606 ditto: exited with 1: ")
    assert shipped(folder) == old


def test_publish_needs_a_rendered_tape(tmp_path, cli, capsys):
    cli(tmp_path, "new", "shop")
    capsys.readouterr()
    assert cli(tmp_path / "shop", "publish", "--story", "starter") == 1
    out, err = capsys.readouterr()
    assert out == "" and as_explained("VT405").fullmatch(err.rstrip("\n"))
    assert not (tmp_path / "shop" / "dist").exists()


def test_a_codesign_that_fails_is_vt606_and_ships_nothing(contrail, cli, capsys, monkeypatch, tmp_path):
    run = publish._run
    monkeypatch.setattr(publish, "_run", lambda *command: run(*command) if command[0] != "codesign" else
                        run("codesign", "--force", "--deep", "--sign", "-", str(tmp_path / "nothing")))
    assert cli(contrail, "publish", "--story", "starter") == 1
    assert as_explained("VT606").fullmatch(refused(contrail, capsys).rstrip("\n"))


def test_a_lock_that_is_not_toml_is_vt605_and_ships_nothing(contrail, cli, capsys):
    (contrail / "videotape.lock").write_text(publish.HEADER + '\n["shop 0.1.0 + starter 1.0.0"]\n<<<<<<< HEAD\n')
    assert cli(contrail, "publish", "--story", "starter") == 1
    out, err = capsys.readouterr()
    assert as_explained("VT605").fullmatch(err.rstrip("\n"))
    assert not (contrail / "dist").exists()


def test_a_key_picture_of_another_size_than_its_clips_is_vt407(contrail, cli, capsys):
    frames.write_png(frames.Frame(640, 352, bytes(640 * 352 * 3)), contrail / "tapes" / "starter" / "keys" / "todo.png")
    assert cli(contrail, "publish", "--story", "starter") == 1
    assert as_explained("VT407").fullmatch(refused(contrail, capsys).rstrip("\n"))


def test_publish_without_ffmpeg_is_doctors_vt102_in_doctors_words(contrail, cli, capsys, monkeypatch, tmp_path):
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "ffprobe").symlink_to(shutil.which("ffprobe"))
    monkeypatch.setenv("PATH", str(tools))
    check = doctor.ffmpeg()
    assert (check.ok, check.fix) == (False, CODES["VT102"].fix)
    assert cli(contrail, "publish", "--story", "starter") == 1
    assert refused(contrail, capsys) == f"error VT102 PATH: {check.what}\nfix: {check.fix}\n"


def test_a_clip_ffmpeg_cannot_encode_is_vt404_naming_the_command(contrail, cli, capsys):
    (contrail / "tapes" / "starter" / "moves" / "opening.mp4").write_bytes(b"not a clip")
    assert cli(contrail, "publish", "--story", "starter") == 1
    err = refused(contrail, capsys).splitlines()
    assert err[0].startswith("error VT404 ffmpeg: ffmpeg -hide_banner -loglevel error -i ")
    assert err[-1] == ("next: run videotape doctor, which checks ffmpeg and ffprobe, then run the command again; when "
                       "ffmpeg names a file of the tape, render the story again first")


def refused(contrail: Path, capsys) -> str:
    """What publish printed when it refused, having shipped and recorded nothing."""
    out, err = capsys.readouterr()
    assert not (contrail / "dist" / "Contrail-starter.app").exists() and not (contrail / "videotape.lock").exists()
    return err


def test_a_tape_older_than_its_sources_is_vt601_naming_what_changed(contrail, cli, capsys):
    screenplay = contrail / "contrail" / "screenplay.py"
    screenplay.write_text(screenplay.read_text() + "\n# a note\n")
    assert cli(contrail, "publish", "--story", "starter") == 1
    err = refused(contrail, capsys)
    assert as_explained("VT601").fullmatch(err.rstrip("\n"))
    assert err.startswith("error VT601 tapes/starter: the app's code changed since the tape was rendered\n")

    steps = contrail / "data" / "steps.json"
    steps.write_text(steps.read_text().replace("Add your data", "Connect your data"))
    pyproject = contrail / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('version = "0.1.0"', 'version = "0.2.0"'))
    assert cli(contrail, "publish", "--story", "starter") == 1
    assert refused(contrail, capsys).startswith("error VT601 tapes/starter: the app's version, the app's code and the "
                                                "data changed since the tape was rendered\n")


def test_a_tape_of_another_screenplay_of_the_same_package_is_vt601(contrail, cli, capsys):
    package = contrail / "contrail"
    (package / "other.py").write_text((package / "screenplay.py").read_text().replace("of two scenes", "of two pages"))
    assert cli(contrail, "render", "--story", "starter", "--model", "stand-in") == 0
    capsys.readouterr()
    pyproject = contrail / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('"contrail.screenplay:app"', '"contrail.other:app"'))
    assert cli(contrail, "publish", "--story", "starter") == 1
    assert refused(contrail, capsys).startswith("error VT601 tapes/starter: the app's screenplay changed since the "
                                                "tape was rendered\n")


def as_wan3(folder: Path) -> dict:
    """Rewrite the tape's made block as a wan3.0 render of the same sources would write it."""
    file = folder / "tapes" / "starter" / "tape.json"
    written = json.loads(file.read_text())
    written["made"] = made.made(project.find(folder), told(folder, "starter"), WAN3)
    file.write_text(json.dumps(written, indent=2) + "\n")
    return written["made"]


def test_a_wan3_tape_is_checked_against_its_sources_without_fal_key(contrail, cli, capsys, monkeypatch):
    monkeypatch.setitem(MODELS, "wan3.0", dataclasses.replace(MODELS["wan3.0"], eye=lambda tape: StandInEye()))
    made_by = as_wan3(contrail)
    assert cli(contrail, "publish", "--story", "starter") == 0
    assert capsys.readouterr().out.splitlines()[-3:-1] == [f"label {LABEL}", f"id {made_by['id']}"]

    steps = contrail / "data" / "steps.json"
    steps.write_text(steps.read_text().replace("Add your data", "Connect your data"))
    assert cli(contrail, "publish", "--story", "starter") == 1
    assert capsys.readouterr().err == ("error VT601 tapes/starter: the data changed since the tape was rendered\n"
                                       "fix: render the tape again with the model that made it, then publish it:\n"
                                       "videotape render --story starter --model wan3.0\n")


def extra_box_on_todo(mode: Mode, prompt: str, seed: int) -> Flaw:
    return Flaw.EXTRA_BOX if mode is Mode.TEXT_TO_VIDEO and '"Make it yours"' in prompt else Flaw.NONE


def test_a_failing_check_nobody_accepted_is_vt602_until_it_is_accepted(contrail, cli, capsys, monkeypatch):
    monkeypatch.setitem(MODELS, "stand-in", Listing(lambda: StandIn(flaw=extra_box_on_todo), lambda tape: StandInEye(),
                                                    limit=8, kind=StandIn))
    shutil.rmtree(contrail / "tapes")
    assert cli(contrail, "render", "--story", "starter", "--model", "stand-in", "--takes", "1") == 1
    capsys.readouterr()
    assert cli(contrail, "publish", "--story", "starter") == 1
    assert as_explained("VT602").fullmatch(refused(contrail, capsys).rstrip("\n"))

    assert cli(contrail, "accept", "todo()", "VT503", "--story", "starter", "--reason", "the stand-in's extra box") == 0
    assert cli(contrail, "publish", "--story", "starter") == 0
    assert capsys.readouterr().out.splitlines()[-1] == "videotape.lock holds the label now; commit it"


def test_a_label_the_lock_holds_with_another_id_is_vt305_until_a_version_is_bumped(contrail, cli, capsys):
    assert cli(contrail, "publish", "--story", "starter") == 0
    capsys.readouterr()
    lock = (contrail / "videotape.lock").read_text()
    steps = contrail / "data" / "steps.json"
    steps.write_text(steps.read_text().replace("Add your data", "Connect your data"))
    assert cli(contrail, "render", "--story", "starter", "--model", "stand-in") == 0
    capsys.readouterr()
    app = (contrail / "dist" / "Contrail-starter.app" / "Contents" / "Resources" / "tape" / "tape.json").read_bytes()

    assert cli(contrail, "publish", "--story", "starter") == 1
    err = capsys.readouterr().err
    assert as_explained("VT305").fullmatch(err.rstrip("\n"))
    assert err.splitlines()[0].endswith(": the data changed")
    assert (contrail / "videotape.lock").read_text() == lock
    assert (contrail / "dist" / "Contrail-starter.app" / "Contents" / "Resources" / "tape" / "tape.json").read_bytes() == app

    pyproject = contrail / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('version = "0.1.0"', 'version = "0.1.1"'))
    assert cli(contrail, "render", "--story", "starter", "--model", "stand-in") == 0
    assert cli(contrail, "publish", "--story", "starter") == 0
    assert list(tomllib.loads((contrail / "videotape.lock").read_text())) == [LABEL, "contrail 0.1.1 + starter 1.0.0"]


TWICE = "in the data folder"


@dataclasses.dataclass(frozen=True)
class Smudging:
    """The stand-in's eye, which reads every time TWICE shows on a frame after the first clear times as smudged."""

    clear: int
    name = "stand-in"

    def see(self, frame: frames.Frame) -> tuple[Spot, ...]:
        shown = itertools.count(1)
        return tuple(dataclasses.replace(spot, text="in the dark folder")
                     if spot.text == TWICE and next(shown) > self.clear else spot for spot in StandInEye().see(frame))


def test_a_line_a_key_shows_twice_is_two_checks_so_the_one_that_passed_failing_after_encoding_is_vt604(
        contrail, cli, capsys, monkeypatch):
    steps = contrail / "data" / "steps.json"
    steps.write_text(steps.read_text().replace("in the stories folder", TWICE))
    eye = lambda clear: Listing(lambda: StandIn(flaw=lambda mode, prompt, seed: Flaw.NONE),
                                lambda tape: Smudging(clear), limit=8, kind=StandIn)
    monkeypatch.setitem(MODELS, "stand-in", eye(1))
    assert cli(contrail, "render", "--story", "starter", "--model", "stand-in", "--takes", "1") == 1
    assert [(failure["shot"], failure["code"], failure["about"]) for failure in
            json.loads((contrail / "tapes" / "starter" / "dailies.json").read_text())["failures"]] == \
        [("key todo()", "VT502", TWICE)]
    assert cli(contrail, "accept", "todo()", "VT502", "--story", "starter", "--reason", "the second line, smudged") == 0
    capsys.readouterr()

    monkeypatch.setitem(MODELS, "stand-in", eye(0))
    assert cli(contrail, "publish", "--story", "starter") == 1
    assert refused(contrail, capsys).startswith(
        "error VT604 moves/home--see-the-steps.mp4: its HEVC last frame, where TapePlayer rests on todo(), fails a "
        f'check its key passed: VT502 {TWICE}: read "in the dark folder", CER ')


def test_a_player_that_does_not_build_is_vt603(contrail, cli, capsys, monkeypatch):
    monkeypatch.setattr(player, "_build", lambda folder: subprocess.CompletedProcess(
        [], 1, "", "xcode-select: error: tool 'xcodebuild' requires Xcode\n** BUILD FAILED **\n"))
    assert cli(contrail, "publish", "--story", "starter") == 1
    assert refused(contrail, capsys).startswith("error VT603 ")


def test_an_encoded_clip_whose_last_frame_fails_a_check_its_key_passed_is_vt604(contrail, cli, capsys, monkeypatch):
    """The encoding here paints the background over todo()'s Back button in the clip that lands on todo()."""
    encode = frames.hevc
    back = manifest(contrail)["scenes"]["todo()"]["hotspots"][0]["box"]

    def spoiling(clip: Path, out: Path) -> None:
        encode(clip, out)
        if clip.name == "home--see-the-steps.mp4":
            painted = out.with_name("painted.mp4")
            box = ":".join(f"{name}={round(back[key] * size)}" for name, key, size in
                           (("x", "x", 1280), ("y", "y", 704), ("w", "w", 1280), ("h", "h", 704)))
            frames._ffmpeg("-i", str(out), "-vf", f"drawbox={box}:color=0x2f6f7e:t=fill", *frames.HEVC, str(painted))
            painted.replace(out)

    monkeypatch.setattr(frames, "hevc", spoiling)
    assert cli(contrail, "publish", "--story", "starter") == 1
    err = refused(contrail, capsys)
    assert as_explained("VT604").fullmatch(err.rstrip("\n"))
    assert [path.name for path in (contrail / "dist").iterdir()] == []
