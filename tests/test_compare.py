import json
import re
import shutil
from pathlib import Path

import pytest

from videotape import frames, ledger
from videotape.cli import main
from videotape.fal import Receipt
from videotape.render import render
from videotape.standin import Flaw, StandIn, StandInEye

SURF_SHOP = Path(__file__).parent.parent / "examples" / "surf_shop"
ENTRANCE_KEY = 'The text reads "How would you like to come in?"'


class Billed(StandIn):
    """Bills each call as Wan 3.0 on fal would, 5.04 seconds of video at ten cents a second."""

    def text_to_video(self, prompt, seed, out):
        super().text_to_video(prompt, seed, out)
        return Receipt(f"key-{seed}", 5.04, 0.504, {})

    def first_last_frame(self, prompt, start, end, seed, out):
        super().first_last_frame(prompt, start, end, seed, out)
        return Receipt(f"move-{seed}", 5.04, 0.504, {})


def drop_an_entrance_button(mode, prompt, seed):
    return Flaw.DROP_BUTTON if ENTRANCE_KEY in prompt else Flaw.NONE


@pytest.fixture(scope="module")
def tapes(tmp_path_factory):
    """A is shaped like the 5B's final tape: no dollars on its takes, 360 GPU seconds each, and one pod at $3.99/h.
    B is billed per call like Wan 3.0, and its entrance key lost a button."""
    directory = tmp_path_factory.mktemp("compare") / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape*", "compare*"))
    a, b = directory / "tape", directory / "tape-b"
    render(directory, StandIn(flaw=lambda *_: Flaw.NONE), StandInEye(), takes=1)
    render(directory, Billed(flaw=drop_an_entrance_button), StandInEye(), takes=1, tape=b)
    record = json.loads((a / "dailies.json").read_text())
    for shot in record["keys"] + record["moves"]:
        for take in shot["takes"]:
            del take["usd"]
            take["seconds"] = 360.0
    (a / "dailies.json").write_text(json.dumps(record))
    ledger.append(a, {"kind": "pod", "at": "2026-11-10T12:23:20+00:00", "pod": "n6lc3mo0get3jw", "gpu": "NVIDIA H100 80GB HBM3",
                      "usd_per_hour": 3.99, "started": "2026-11-10T11:30:59+00:00", "stopped": "2026-11-10T12:23:20+00:00",
                      "seconds": 3141, "usd": 3.4813})
    return directory, a, b


@pytest.fixture(scope="module")
def compared(tapes):
    directory, a, b = tapes
    assert main(["compare", str(a), str(b)]) == 0
    return directory, (directory / "compare.html").read_text()


def side(page: str, number: int, letter: str) -> str:
    card = page.split(f'<section class="shot" id="shot-{number}">')[1].split("</section>")[0]
    return card.split(f"<strong>{letter}. ")[1].split("</figure>\n")[0]


def test_compare_writes_its_page_beside_the_tapes_and_prints_each_tapes_totals(tapes, capsys):
    directory, a, b = tapes
    assert main(["compare", str(a), str(b)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"A {a}  stand-in  1280x704 at 24 fps  10 takes  $3.48  buttons found 5 of 5"
    assert lines[1] == f"B {b}  stand-in  1280x704 at 24 fps  10 takes  $5.04  buttons found 4 of 5"
    assert lines[2] == f"wrote {directory / 'compare.html'} with 50 stills in {directory / 'compare-frames'}"
    assert (directory / "compare.html").is_file()


def test_every_shot_is_matched_by_title_with_both_kept_takes_side_by_side(compared):
    directory, page = compared
    titles = re.findall(r'<h2>\d+\. (.*?) \((?:text-to-video|first-and-last-frame)\)</h2>', page)
    assert titles == ["key welcome", "key entrance", "key login", "key signup", "key gallery",
                      "welcome -&gt; entrance &quot;Enter shop&quot;", "entrance -&gt; login &quot;I have an account&quot;",
                      "entrance -&gt; signup &quot;Create an account&quot;", "entrance -&gt; gallery &quot;Browse as guest&quot;",
                      "signup -&gt; login &quot;Sign up&quot;"]
    for number in range(1, 11):
        for letter, tape in (("A", "tape"), ("B", "tape-b")):
            [video] = re.findall(r'<video src="([^"]+)" autoplay loop muted', side(page, number, letter))
            assert video.startswith(f"{tape}/takes/") and (directory / video).is_file()
    linked = re.findall(r'(?:src|href)="([^"]+)"', page)
    keys, moves = 5 * 2 * 2, 5 * 2 * 6
    assert len(linked) == keys + moves + 2
    assert all((directory / path).is_file() for path in linked)


def test_each_key_shows_every_button_found_or_not_and_every_reading_with_its_cer(compared):
    _, page = compared
    entrance_a, entrance_b = side(page, 2, "A"), side(page, 2, "B")
    assert 'src="tape/keys/entrance.png"' in entrance_a and 'src="tape-b/keys/entrance.png"' in entrance_b
    assert "3 of 3 buttons found." in entrance_a
    assert '<p class="note fail">2 of 3 buttons found.</p>' in entrance_b
    [dropped] = re.findall(r'button &quot;([^&]+)&quot;</span><span class="result">not found', entrance_b)
    assert f'text &quot;{dropped}&quot;</span><span class="result">read ' in entrance_b
    assert "not found" not in entrance_a
    for text in ("How would you like to come in?", "I have an account", "Create an account", "Browse as guest"):
        assert (f'text &quot;{text}&quot;</span><span class="result">read &quot;{text}&quot;, CER 0.000') in entrance_a
    assert "5 of 5 buttons found, 15 of 15 lines and labels read exactly" in page
    assert "4 of 5 buttons found, 14 of 15 lines and labels read exactly" in page


def test_each_move_shows_its_seams_and_five_frames_from_its_first_to_its_last(tapes, compared, tmp_path):
    directory, a, _ = tapes
    _, page = compared
    enter = side(page, 6, "A")
    assert re.search(r"Seams: leaves welcome by 0\.0[0-4]\d, enters entrance by 0\.0[0-4]\d\.", enter)
    assert re.search(r"Each frame differs from the next by 0\.\d{4} on average\.", enter)
    stills = re.findall(r'<img src="(compare-frames/a/welcome--enter-shop-\d{3}\.png)" alt="(\d+)% of the move in A"', enter)
    assert [(path.rsplit("-", 1)[1], percent) for path, percent in stills] == [
        ("000.png", "0"), ("025.png", "25"), ("050.png", "50"), ("075.png", "75"), ("100.png", "100")]
    shown = [frames.read_png(directory / path) for path, _ in stills]
    assert {(still.width, still.height) for still in shown} == {(480, 264)}
    keys = [tmp_path / "welcome.png", tmp_path / "entrance.png"]
    for key, out in zip(("welcome", "entrance"), keys):
        frames.stills(a / "keys" / f"{key}.png", (0.0,), 480, [out])
    welcome, entrance = (frames.read_png(key) for key in keys)
    assert frames.difference(shown[0], welcome) < 0.01 and frames.difference(shown[-1], entrance) < 0.01
    assert frames.difference(shown[1], welcome) > 0.01 and frames.difference(shown[1], entrance) > 0.01


def test_each_shot_shows_its_render_time_and_cost_on_its_tapes_terms(compared):
    _, page = compared
    assert ("Kept take rendered in 360.0 s. 1 take in 360.0 s for $0.40, GPU time at the pod&#x27;s $3.99/h, "
            "setup excluded.") in side(page, 1, "A")
    assert re.search(r"Kept take rendered in \d+\.\d s\. 1 take in \d+\.\d s for \$0\.50, as billed per call\.",
                     side(page, 6, "B"))
    assert page.count("Kept take rendered in ") == 20
    assert "$3.48 in the ledger; the takes cost $3.99, GPU time at the pod&#x27;s $3.99/h, setup excluded" in page
    assert "$5.04 in the ledger; the takes cost $5.04, as billed per call" in page
    assert "1280x704 at 24 fps" in page and "1 pod for 0.873 h with setup" in page


def test_a_shot_only_one_tape_has_is_shown_as_missing_from_the_other(tapes, tmp_path, capsys):
    directory, a, _ = tapes
    edited = tmp_path / "surf_shop"
    shutil.copytree(SURF_SHOP, edited, ignore=shutil.ignore_patterns("tape*", "compare*"))
    screenplay = edited / "screenplay.py"
    screenplay.write_text(screenplay.read_text().replace('"Browse as guest": "gallery"', '"Look around": "gallery"'))
    other = directory / "tape-edited"
    render(edited, StandIn(flaw=lambda *_: Flaw.NONE), StandInEye(), takes=1, tape=other)
    assert main(["compare", str(a), str(other)]) == 0
    page = (directory / "compare.html").read_text()
    assert "<h2>9. entrance -&gt; gallery &quot;Browse as guest&quot; (first-and-last-frame)</h2>" in page
    assert "<h2>11. entrance -&gt; gallery &quot;Look around&quot; (first-and-last-frame)</h2>" in page
    assert page.count("This shot is not in this tape.") == 2
    assert page.split('id="shot-2">')[1].split("</section>")[0].count("prompts differ") == 1


def test_compare_names_a_folder_that_is_not_a_tape(tapes, capsys):
    directory, a, _ = tapes
    assert main(["compare", str(a), str(directory / "tape-none")]) == 1
    assert capsys.readouterr().err == f"error: no tape.json in {directory / 'tape-none'}; render a screenplay into it first\n"
