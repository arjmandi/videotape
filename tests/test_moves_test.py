"""scripts/moves-test judges the ten labelled moves of 2026-11-10 with the two checks a render makes of every move's
take, VT506 and VT507, and shows where each agrees with the labels. No test sends a request: Claude answers a judgment
from what the stand-in's judge sees, through a fake network, as in tests/test_claude.py. The ten labelled clips, under
examples/surf_shop and never in the repo, are judged when they are there: VT506 live, and VT507 from the fixture of
Claude's recorded answers, which the paid run writes with --fixture."""

import base64
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import shutil
import sys
import uuid
from pathlib import Path

import pytest

from conftest import CONTRAIL, FIXTURES, contrail_copy, forget
from test_claude import KEY as CLAUDE_KEY, Claude, message
from test_screen_test import Page
from videotape import claude, frames, project
from videotape.checks import FRAMES, Cut
from videotape.claude import ClaudeJudge
from videotape.standin import StandInJudge

ROOT = CONTRAIL.parent.parent
CLIPS = ROOT / "examples" / "surf_shop"
FIXTURE = FIXTURES / "recorded" / "moves" / "calibration.json"
"""Claude's recorded answers to the ten labelled clips, which the paid run writes with --fixture."""
MOST = 5 * claude.judge_estimate(1280, 704) + 5 * claude.judge_estimate(1280, 720)
"""The most the ten judgments cost: Wan 2.2 5B's five clips are 1280x704, and Wan 3.0's five 1280x720."""


@pytest.fixture(scope="module")
def script():
    loader = importlib.machinery.SourceFileLoader("moves_test", str(ROOT / "scripts" / "moves-test"))
    spec = importlib.util.spec_from_loader("moves_test", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def keyless(monkeypatch):
    for key in ("FAL_KEY", "ANTHROPIC_API_KEY", "RUNPOD_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def moves(script, directory: Path, *arguments: str) -> tuple[int, str, str]:
    """Run the script in this process on a project, from the repo's root, with Contrail's modules forgotten before and
    after so each copy is imported afresh."""
    out, err = io.StringIO(), io.StringIO()
    forget(project.find(directory))
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = script.main([str(directory), *arguments])
    finally:
        forget(project.find(directory))
    return code, out.getvalue(), err.getvalue()


def calibration_line(judge: str = "claude-opus-5-5", cost: str = f"at most ${MOST:.2f}") -> str:
    if CLIPS.is_dir():
        return (f"calibration: 10 labelled clips under examples/surf_shop, their scene scores free, and 10 judgments of "
                f"{FRAMES} frames each by {judge}, {cost}")
    return "calibration: no clips folder at examples/surf_shop, so none"


HEAD = "moves test on gemini-omni-flash-1.2, judged by claude-opus-5-5: the ten labelled moves of 2026-11-10"
needs_clips = pytest.mark.skipif(not CLIPS.is_dir(), reason=f"the ten labelled clips are not at {CLIPS}")


def test_the_estimate_counts_a_judgment_of_each_labelled_clip_and_needs_no_api_key(script, tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    directory = contrail_copy(tmp_path / "contrail")
    code, out, err = moves(script, directory, "--estimate")
    assert (code, err) == (0, "")
    cost = f"the moves test: at most ${MOST:.2f}, no cap" if CLIPS.is_dir() else "the moves test: free"
    assert out.splitlines() == [HEAD, calibration_line(), cost]
    assert 1 < MOST < 2
    code, out, _ = moves(script, directory, "--estimate", "--cap-usd", "5")
    assert code == 0 and out.splitlines()[-1] == (f"the moves test: at most ${MOST:.2f}, under the cap of $5.00 at the most"
                                                  if CLIPS.is_dir() else "the moves test: free")
    code, out, _ = moves(script, directory, "--estimate", "--model", "stand-in")
    assert code == 0 and out.splitlines() == ["moves test on stand-in, judged by stand-in: the ten labelled moves of "
                                              "2026-11-10", calibration_line("stand-in", "free"), "the moves test: free"]
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


@needs_clips
def test_a_most_past_the_cap_or_no_cap_stops_before_any_call_and_names_the_cap_the_test_needs(script, tmp_path,
                                                                                            monkeypatch):
    monkeypatch.chdir(ROOT)
    directory = contrail_copy(tmp_path / "contrail")
    needed = f"{__import__('math').ceil(MOST * 100) / 100:.2f}"
    code, out, err = moves(script, directory, "--cap-usd", "1")
    assert code == 1 and out.splitlines()[-1].endswith("past the cap of $1.00 at the most")
    assert err == (f"error VT402 before the first call: the moves test costs at most ${MOST:.2f}, which passes the "
                   f"cap of $1.00\nnext: run it with a cap of at least ${needed}, as in:\nuv run scripts/moves-test "
                   f"{directory} --cap-usd {needed}\n")
    code, _, err = moves(script, directory)
    assert code == 1 and err == ("error VT402 before the first call: claude-opus-5-5 bills per judgment, and no cap is "
                                 "set\nnext: set the most the moves test may spend, as in:\n"
                                 f"uv run scripts/moves-test {directory} --cap-usd {needed}\n")
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


@needs_clips
def test_a_missing_api_key_stops_the_moves_test_before_any_call_as_vt104(script, tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    directory = contrail_copy(tmp_path / "contrail")
    code, out, err = moves(script, directory, "--cap-usd", "5")
    assert (code, err) == (1, "error VT104 .env: claude-opus-5-5, the judge of this model's moves, needs ANTHROPIC_API_KEY, "
                              "and it is not in the environment or .env\nfix: copy .env.example to .env and set "
                              "ANTHROPIC_API_KEY there, or export it\n")
    assert out.splitlines()[:2] == [HEAD, calibration_line()]
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


class Judging(Claude):
    """Claude's fake network, which answers a judgment from the stand-in's judge."""

    def read(self, request):
        body = json.loads(request.data)
        images = [part for part in body["messages"][0]["content"] if part["type"] == "image"]
        pictures = [frames.png_frame(base64.b64decode(image["source"]["data"])) for image in images]
        verdict = StandInJudge().judge(list(enumerate(pictures)))
        answer = {"frames": [{"overlaid": overlaid, "seen": seen} for overlaid, seen in zip(verdict.overlaid, verdict.seen)]}
        return {**message(json.dumps(answer)), "id": f"msg_{uuid.uuid4().hex[:24]}"}


def fake(patch: pytest.MonkeyPatch) -> Judging:
    hosted = Judging()
    patch.setattr(claude, "_urlopen", hosted)
    patch.setenv("ANTHROPIC_API_KEY", CLAUDE_KEY)
    return hosted


RUN = ("--cap-usd", "5")


@pytest.fixture(scope="module")
def tested(script, tmp_path_factory):
    """The moves test on a copy of Contrail, judged by Claude through the fake network, run once for the tests that
    read it."""
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(ROOT)
        hosted = fake(patch)
        directory = contrail_copy(tmp_path_factory.mktemp("tested") / "contrail")
        return directory, hosted, moves(script, directory, *RUN)


def copied(tested, to: Path) -> Path:
    return Path(shutil.copytree(tested[0], to / "contrail", ignore=shutil.ignore_patterns("__pycache__")))


def ledger_lines(directory: Path) -> list[dict]:
    return [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines()]


def report(directory: Path) -> tuple[str, Page]:
    page = (directory / "tapes" / "moves-test" / "report.html").read_text()
    return page, Page(page)


@needs_clips
def test_it_judges_every_labelled_clip_and_pays_for_each_judgment_under_the_cap(tested, script):
    directory, hosted, (code, out, err) = tested
    assert (code, err) == (0, "")
    lines = ledger_lines(directory)
    assert [(line["kind"], line["tape"], line["model"], line["seed"]) for line in lines] == [
        ("judgment", "tapes/moves-test/calibration", "claude-opus-5-5", 1)] * 10
    assert [line["shot"] for line in lines] == list(script.LABELS)
    assert len(hosted.seen) == 10 and 0 < sum(line["usd"] for line in lines) <= 5
    printed = out.splitlines()
    assert printed[:3] == [HEAD, calibration_line(), f"the moves test: at most ${MOST:.2f}, under the cap of $5.00 at the most"]
    assert printed[3] == f"calibration: 10 labelled clips judged by claude-opus-5-5 -> {directory}/tapes/moves-test/calibration"
    judged = [line for line in printed if "  labelled VT50" in line]
    assert len(judged) == 10 and all(line.endswith(" judged") for line in judged)
    assert judged[0].startswith("1. tape/moves/entrance--browse-as-guest.mp4  labelled VT507, VT506 0.167 passed, VT507 ")
    assert printed[-2] == f"wrote {directory}/tapes/moves-test/report.html"
    assert printed[-1].startswith("the calibration: VT506 agrees with the labels on 10 of 10 clips, VT507 on ")
    assert len(list((directory / "tapes" / "moves-test" / "calibration" / "looks").iterdir())) == 10
    assert len(list((directory / "tapes" / "moves-test" / "calibration" / "frames").iterdir())) == 10 * FRAMES


@needs_clips
def test_run_again_it_judges_nothing_and_writes_the_same_report(tested, script, tmp_path, monkeypatch):
    directory = copied(tested, tmp_path)
    monkeypatch.chdir(ROOT)
    hosted = fake(monkeypatch)
    ledger_before = (directory / "ledger.jsonl").read_text()
    report_before = (directory / "tapes" / "moves-test" / "report.html").read_text()
    code, out, err = moves(script, directory, *RUN)
    assert (code, err) == (0, "") and hosted.seen == []
    assert (directory / "ledger.jsonl").read_text() == ledger_before
    assert (directory / "tapes" / "moves-test" / "report.html").read_text() == report_before
    assert sum(line.endswith(" overlaid, cached") for line in out.splitlines()) == 10


@needs_clips
def test_the_cap_counts_what_the_calibration_already_spent_stops_before_the_judgment_that_would_pass_it_and_still_writes_the_report(
        script, tmp_path, monkeypatch):
    directory = contrail_copy(tmp_path / "contrail")
    monkeypatch.chdir(ROOT)
    fake(monkeypatch)
    earlier = {"kind": "judgment", "tape": "tapes/moves-test/calibration", "shot": "tape/moves/welcome--enter-shop.mp4",
               "seed": 1, "seconds": 0.0, "usd": 4.9, "request_id": "earlier"}
    (directory / "ledger.jsonl").write_text(json.dumps(earlier) + "\n")
    code, out, err = moves(script, directory, *RUN)
    assert code == 1
    assert err.startswith("error VT402 tape/moves/entrance--browse-as-guest.mp4: the next judgment would pass the moves "
                          "test's cap of $5.00, with $4.90 spent")
    assert err.endswith("next: run the moves test again with a higher cap, which resumes, as in:\nuv run "
                        f"scripts/moves-test {directory} --cap-usd 10.00\n")
    assert sum(line.get("usd", 0.0) for line in ledger_lines(directory)) == 4.9
    assert "the report shows what was judged before it" in err
    assert sum(line.endswith(" VT507 not judged, the cap") for line in out.splitlines()) == 10
    _, shown = report(directory)
    [calibration] = shown.all("section", id="calibration")
    assert (calibration["data-vt506"], calibration["data-vt507"]) == ("10 of 10", "0 of 0")
    assert {figure["data-overlaid"] for figure in shown.all("figure") if "data-frame" in figure} == {"unjudged"}


@needs_clips
def test_the_report_shows_each_labelled_clip_with_its_frames_the_judges_answers_the_checks_and_where_each_agrees(tested):
    directory, _, _ = tested
    page, parsed = report(directory)
    [calibration] = parsed.all("section", id="calibration")
    assert calibration["data-vt506"] == "10 of 10"
    labelled = {figure["data-clip"]: (figure["data-label"], figure["data-vt506"], figure["data-vt507"])
                for figure in parsed.all("figure") if "data-label" in figure}
    assert len(labelled) == 10 and all(agrees == "agrees" for _, agrees, _ in labelled.values())
    assert labelled["tape-wan3/moves/signup--sign-up.mp4"][0] == "VT506"
    assert {said for _, _, said in labelled.values()} <= {"agrees", "disagrees"}
    frames_shown = [figure for figure in parsed.all("figure") if "data-frame" in figure]
    assert len(frames_shown) == 10 * FRAMES and {figure["data-overlaid"] for figure in frames_shown} <= {"yes", "no"}
    pictures = {attrs["src"] for attrs in parsed.all("img")}
    assert len(pictures) == 10 * FRAMES and all((directory / "tapes" / "moves-test" / picture).is_file() for picture in pictures)
    assert all(not picture.startswith("/") for picture in pictures)
    assert "VT506 frame" in parsed.text and "VT507 " in parsed.text and "judged by claude-opus-5-5" in parsed.text
    assert "color-scheme: light dark" in page and "prefers-color-scheme: dark" in page
    assert "http://" not in page.replace("http://www.w3.org", "") and "<script" not in page
    assert "ffmpeg.org/ffmpeg-filters.html" in page and "platform.claude.com" in page


def test_the_report_without_the_clips_says_which_folder_is_missing(script, tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    directory = contrail_copy(tmp_path / "contrail")
    code, out, err = moves(script, directory, "--model", "stand-in", "--clips", str(tmp_path / "nowhere"))
    assert (code, err) == (0, "")
    assert out.splitlines() == ["moves test on stand-in, judged by stand-in: the ten labelled moves of 2026-11-10",
                                f"calibration: no clips folder at {tmp_path / 'nowhere'}, so none", "the moves test: free",
                                f"wrote {directory}/tapes/moves-test/report.html"]
    page, parsed = report(directory)
    assert "No labelled clips" in parsed.text and "Name it with --clips." in parsed.text
    assert not (directory / "ledger.jsonl").exists()


# The calibration.

@needs_clips
def test_the_cut_check_agrees_with_the_labels_on_the_ten_clips(script):
    """Run live: ffmpeg scores every frame of each clip. The three cuts score 0.319 and up, the dissolves 0.187 and
    under, and 0.3 parts them."""
    tops = {}
    for clip, fails in script.LABELS.items():
        cut = Cut(tuple(frames.scene_scores(CLIPS / clip)))
        tops[clip] = cut.top[1]
        assert cut.passed == (fails != "VT506"), f"{clip}: {cut.top}"
    assert max(score for clip, score in tops.items() if script.LABELS[clip] == "VT507") < 0.19
    assert min(score for clip, score in tops.items() if script.LABELS[clip] == "VT506") > 0.31


@needs_clips
@pytest.mark.skipif(not FIXTURE.is_file(), reason=f"no recorded answers at {FIXTURE}; the paid run writes them with "
                                                  "--fixture")
def test_the_dissolve_check_agrees_with_the_labels_on_claudes_recorded_answers(script, tmp_path, monkeypatch):
    """Replays the text of Claude's answers to the ten clips, which the paid run recorded, against frames sampled
    live. The answers hold only for the question they answered: a changed prompt or rule needs a new paid run."""
    recorded = json.loads(FIXTURE.read_text())
    assert recorded["test"] == "moves-test" and recorded["judge"] == "claude-opus-5-5"
    assert recorded["asked"] == claude.asked(), ("the judge's prompt, schema or settings changed since the answers were "
                                                 "recorded; run the paid calibration again with --fixture")
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLAUDE_KEY)
    for clip, fails in script.LABELS.items():
        assert clip in recorded["clips"], f"no recorded answer for {clip}"
        judge = ClaudeJudge(tmp_path / clip, send=Claude(message(recorded["clips"][clip]["reply"])))
        verdict = judge.judge(frames.sampled(CLIPS / clip, FRAMES))
        assert verdict.passed == (fails != "VT507"), f"{clip}: {verdict.overlaid} {verdict.seen}"


@needs_clips
def test_the_fixture_flag_writes_the_judges_recorded_answers_to_the_labelled_clips_text_only(tested, script, tmp_path,
                                                                                            monkeypatch):
    directory = copied(tested, tmp_path)
    monkeypatch.chdir(ROOT)
    hosted = fake(monkeypatch)
    code, out, err = moves(script, directory, *RUN, "--fixture", str(tmp_path / "recorded" / "calibration.json"))
    assert (code, err) == (0, "") and hosted.seen == []
    assert f"wrote {tmp_path / 'recorded' / 'calibration.json'}: 10 recorded answers" in out.splitlines()
    held = json.loads((tmp_path / "recorded" / "calibration.json").read_text())
    assert (held["test"], held["judge"], held["asked"]) == ("moves-test", "claude-opus-5-5", claude.asked())
    assert sorted(held["clips"]) == sorted(script.LABELS)
    for clip, answer in held["clips"].items():
        assert set(answer) == {"model", "reply", "tokens", "usd"}
        assert len(json.loads(answer["reply"])["frames"]) == FRAMES and "data:" not in answer["reply"]
    code, _, err = moves(script, directory, "--model", "stand-in", "--fixture", str(tmp_path / "none.json"))
    assert code == 1 and err.startswith("error VT110 --fixture: holds claude-opus-5-5's answers, and stand-in's judge is stand-in")
