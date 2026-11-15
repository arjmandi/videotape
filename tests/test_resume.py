"""A model that bills per call renders under a cap. The render stops before the call that would pass it, and run again
with a higher cap it resumes: every take on disk is reused, and no take is submitted or paid for twice."""

import json
from pathlib import Path

import pytest

from conftest import as_explained, copy_of, videotape
from videotape import dailies, ledger
from videotape.fal import Price, Receipt
from videotape.model import MODELS, Listing
from videotape.plan import Mode
from videotape.standin import Flaw, StandIn, StandInEye

PRICE = Price(usd_per_second=0.10, seconds=5)
RENDER = ("render", "--story", "chalk")
THANKS_LATTE = '"One Latte coming up."'
DONE = 'The button "Done" is pressed.'


def flaws(mode: Mode, prompt: str, seed: int) -> Flaw:
    """thanks(Latte) and both Done moves need three takes. The other eight shots pass at their first."""
    if THANKS_LATTE in prompt:
        return {1: Flaw.MISSPELL, 2: Flaw.DROP_LINE}.get(seed, Flaw.NONE)
    if DONE in prompt:
        return {1: Flaw.WRONG_START, 2: Flaw.WRONG_END}.get(seed, Flaw.NONE)
    return Flaw.NONE


CALLS = 8 + 3 * 3
"""The takes a render of the cafe films with these flaws."""


class Metered(StandIn):
    """Bills each submit fifty cents, five seconds at ten cents a second, and numbers its requests."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.submitted = 0

    def text_to_video(self, prompt, seed, out):
        super().text_to_video(prompt, seed, out)
        return self._receipt()

    def first_last_frame(self, prompt, start, end, seed, out):
        super().first_last_frame(prompt, start, end, seed, out)
        return self._receipt()

    def _receipt(self) -> Receipt:
        self.submitted += 1
        return Receipt(f"request-{self.submitted}", 5.0, PRICE.usd, {"result": {"request": self.submitted}})


def metered(monkeypatch, **flaw) -> Metered:
    model = Metered(**flaw)
    monkeypatch.setitem(MODELS, "stand-in", Listing(lambda: model, lambda tape: StandInEye(), price=PRICE, limit=2))
    return model


def tape_files(tape: Path) -> dict[str, bytes]:
    return {path.relative_to(tape).as_posix(): path.read_bytes()
            for path in [tape / "tape.json", *sorted((tape / "keys").iterdir()), *sorted((tape / "moves").iterdir())]}


def test_a_paid_model_with_no_cap_does_not_start(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    model = metered(monkeypatch, flaw=flaws)
    assert cli(directory, *RENDER) == 1
    out, err = capsys.readouterr()
    assert out == "stand-in: 11 shots, 11 to 44 calls, $5.50 to $22.00 at $0.10/s, no cap, $0.00 spent\n"
    assert err.splitlines() == [
        "error VT402 before the first call: stand-in bills per call, and no cap is set",
        "next: set the most this render may spend, as in videotape render --story chalk --cap-usd 20, or for good in "
        "[tool.videotape]:", "cap_usd = 20"]
    assert model.calls == [] and not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


def test_a_render_stops_at_the_cap_resumes_with_a_higher_one_and_pays_for_each_take_once(tmp_path, cli, capsys,
                                                                                            monkeypatch):
    directory = copy_of("cafe", tmp_path / "capped")
    model = metered(monkeypatch, flaw=flaws)
    assert cli(directory, *RENDER, "--cap-usd", "3") == 1
    out, err = capsys.readouterr()
    assert out.splitlines()[0] == "stand-in: 11 shots, 11 to 44 calls, $5.50 to $22.00 at $0.10/s, cap $3.00, $0.00 spent"
    stop = [line for line in err.splitlines() if line.startswith("error VT402 ")]
    assert len(stop) == 1 and " take " in stop[0] and ": the next call would pass the cap of $3.00, with $" in stop[0]
    assert stop[0].endswith(" reserved for the calls in flight, at the listed price of $0.50 a call")
    assert err.splitlines()[-2:] == ["next: raise the cap and run the render again, which resumes:",
                                     "videotape render --story chalk --cap-usd 3.00"]
    assert as_explained("VT402").search(err)
    book = ledger.of(directory, directory / "tapes" / "chalk")
    stopped_lines = book.lines()
    assert len(stopped_lines) == model.submitted == len(model.calls) <= 6
    assert book.totals()["usd"] == 0.5 * model.submitted <= 3.0
    assert not (directory / "tapes" / "chalk" / "tape.json").exists()
    partial = dailies.read(directory / "tapes" / "chalk")
    assert partial["complete"] is False and len(partial["keys"]) + len(partial["moves"]) < 11
    done = [line for line in out.splitlines()[1:] if line[0].isdigit()]
    assert len(done) == len(partial["keys"]) + len(partial["moves"])

    assert cli(directory, *RENDER, "--cap-usd", "20") == 0
    out, err = capsys.readouterr()
    assert out.splitlines()[0] == (f"stand-in: 11 shots, 11 to 44 calls, $5.50 to $22.00 at $0.10/s, cap $20.00, "
                                   f"${0.5 * len(stopped_lines):.2f} spent")
    assert err == ""
    assert model.submitted == len(model.calls) == CALLS
    lines = book.lines()
    assert len(lines) == CALLS and len({(line["shot"], line["seed"]) for line in lines}) == CALLS
    assert {line["request_id"] for line in lines} == {f"request-{n}" for n in range(1, CALLS + 1)}
    assert all(line["usd"] == 0.5 for line in lines) and book.totals()["usd"] == 0.5 * CALLS
    record = dailies.read(directory / "tapes" / "chalk")
    assert record["complete"] is True and record["ledger"]["usd"] == 8.5
    cached = sum(take["cached"] for shot in record["keys"] + record["moves"] for take in shot["takes"])
    assert cached == len(stopped_lines)

    straight = copy_of("cafe", tmp_path / "straight")
    other = metered(monkeypatch, flaw=flaws)
    assert cli(straight, *RENDER, "--cap-usd", "20") == 0
    assert other.submitted == CALLS
    assert tape_files(directory / "tapes" / "chalk") == tape_files(straight / "tapes" / "chalk")
    kept = lambda tape: [(shot["title"], next(t["seed"] for t in shot["takes"] if t["kept"]))
                         for shot in (*dailies.read(tape)["keys"], *dailies.read(tape)["moves"])]
    assert kept(directory / "tapes" / "chalk") == kept(straight / "tapes" / "chalk")


def test_the_cap_in_the_project_counts_what_the_tape_already_spent(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    model = metered(monkeypatch, flaw=flaws)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + "cap_usd = 8.5\n")
    assert cli(directory, *RENDER) == 0
    assert model.submitted == CALLS
    capsys.readouterr()
    heading = directory / "cafe.py"
    heading.write_text(heading.read_text().replace('vt.Heading("Corner Cafe")', 'vt.Heading("The Corner Cafe")'))
    assert cli(directory, *RENDER) == 1
    out, err = capsys.readouterr()
    assert out.splitlines()[0].endswith(", cap $8.50, $8.50 spent")
    assert "the next call would pass the cap of $8.50, with $8.50 spent on this tape" in err
    assert model.submitted == CALLS
    # The new heading films the menu key again and the four moves pinned to it, two of which need three takes.
    assert cli(directory, *RENDER, "--cap-usd", "14") == 0
    assert model.submitted == CALLS + 9
    assert json.loads((directory / "tapes" / "chalk" / "tape.json").read_text())["scenes"]["menu()"]["words"][0] == \
        "The Corner Cafe"


@pytest.mark.parametrize("cap, shown", [("-1", "-1"), ('"nope"', "'nope'"), ("true", "True")])
def test_a_cap_that_is_not_dollars_is_refused(tmp_path, cap, shown):
    directory = copy_of("cafe", tmp_path)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + f"cap_usd = {cap}\n")
    result = videotape(directory, *RENDER)
    assert (result.stdout, result.returncode) == ("", 1)
    assert result.stderr == f"error: pyproject.toml: [tool.videotape] cap_usd is {shown}, not a number of dollars\n"
