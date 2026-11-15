"""The checks over every reader of a key's picture: what each reader reports, what the checks judge from it, and what
the record keeps. The readers here are the stand-in's own and readers made up for a test, which report what they are
given, so no test loads a model or sends a request."""

import dataclasses
import json
from dataclasses import replace
from datetime import date

import pytest

import videotape as vt
from conftest import CONTRAIL, a_story, copy_of, planned, words
from videotape import dailies, standin
from videotape.checks import Chart, Free, Read, Spot, score
from videotape.frames import Box
from videotape.model import MODELS, Listing
from videotape.plan import Key, plan
from videotape.standin import StandIn, StandInEye


def key_of(*elements) -> Key:
    """The key of an app of one scene that shows these elements."""
    app = vt.Screenplay("Test")
    app.scene(lambda: list(elements)).name = "home"
    return plan(app).keys[0]


def spots(*texts: str, controls: tuple[str, ...] = ()) -> tuple[Spot, ...]:
    """Spots as a reader reports them, each at its own place, and the named ones controls."""
    return tuple(Spot(text, Box(0, 40 * number, 100, 33), text in controls) for number, text in enumerate(texts))


def drawn(key: Key) -> tuple:
    """The stand-in's picture of a key from its prompt, and what its eye reads on it."""
    prompt = words(key, a_story())
    frame, _ = standin.draw(standin.quoted(prompt), prompt)
    return frame, StandInEye().see(frame)


def failed(checks) -> list[tuple[str, str]]:
    return [(item.code, item.about) for item in checks.failures]


def test_a_line_passes_vt502_only_when_every_reader_reads_it_exactly_and_the_record_keeps_each_reading():
    key = key_of(vt.Heading("Thanks"), vt.Text("One Latte coming up."))
    exact = Read("stand-in", spots("Thanks", "One Latte coming up."))
    checks = score(key, [exact, replace(exact, reader="second")])
    assert checks.passed and checks.readers == ("stand-in", "second")
    second = Read("second", spots("Thanks", "One Latte coming up"))
    checks = score(key, [exact, second])
    assert failed(checks) == [("VT502", "One Latte coming up.")]
    [item] = checks.failures
    assert item.result == ('read "One Latte coming up." by stand-in and "One Latte coming up" by second, '
                           "CER 0.000 and 0.050")
    assert [(seen.reader, seen.text, seen.cer) for seen in item.readings] == [
        ("stand-in", "One Latte coming up.", 0.0), ("second", "One Latte coming up", 0.05)]
    assert item.box == exact.spots[1].box and item.element == "Text"
    thanks = checks.items()[0]
    assert (thanks.code, thanks.passed, [seen.reader for seen in thanks.readings]) == ("VT502", True, ["stand-in", "second"])
    assert checks.rank(1) > score(key, [exact]).rank(1)


def test_an_action_is_found_only_when_every_reader_finds_it_and_the_hotspot_is_the_first_readers_box():
    key = key_of(vt.Heading("Thanks"), vt.Button("Order", to=key_of(vt.Text("Done")).state))
    first = Read("stand-in", spots("Thanks", "Order", controls=("Order",)))
    second = Read("second", (Spot("Thanks", Box(5, 5, 90, 30), False), Spot("Order", Box(7, 47, 90, 30), True)))
    checks = score(key, [first, second])
    assert checks.hotspots == {"Order": first.spots[1].box} and checks.passed
    [found] = [item for item in checks.items() if item.code == "VT501"]
    assert (found.element, [seen.reader for seen in found.readings]) == ("Button", ["stand-in", "second"])
    checks = score(key, [first, Read("second", spots("Thanks"))])
    assert checks.hotspots == {"Order": None}
    assert [(item.code, item.about, item.result) for item in checks.failures] == [
        ("VT501", "Order", "not found, by second"), ("VT502", "Order", 'read "Order" by stand-in and nothing by second, '
                                                                        "CER 0.000 and 1.000")]


def test_every_check_item_names_the_element_type_it_judges():
    key = next(key for key in planned(CONTRAIL).keys if key.state.name == "profile()")
    frame, seen = drawn(key)
    bar, line = (element.chart for element in key.shown if element.chart)
    profile = next(spot.box for spot in seen.spots if spot.text == "Profile")
    charted = Read("made-up", seen.spots, marked=(profile,), charts=(bar, line))
    items = score(key, [seen, charted]).items()
    by_code = {}
    for item in items:
        by_code.setdefault(item.code, set()).add(item.element)
    assert by_code == {"VT501": {"Tabs"}, "VT502": {"Heading", "Text", "BarChart", "LineChart", "Tabs"},
                       "VT504": {"BarChart", "LineChart"}, "VT509": {"Tabs"}}
    assert all(item.passed for item in items)
    assert [item.element for item in items if item.code == "VT504"] == ["BarChart", "LineChart"]


def tabbed() -> Key:
    """The key of a home scene whose tabs lead to it and to a trips scene, so that Home is its chosen tab."""
    app = vt.Screenplay("Test")

    @app.scene
    def home():
        return [vt.Heading("Home"), vt.Tabs({"Home": home(), "Trips": trips()})]

    @app.scene
    def trips():
        return [vt.Heading("Trips"), vt.Tabs({"Home": home(), "Trips": trips()})]

    return plan(app).keys[0]


def test_the_stand_in_draws_the_chosen_line_inverted_and_its_eye_reports_it_marked_so_vt509_needs_no_paid_call():
    key = tabbed()
    assert 'with "Home" chosen' in words(key, a_story())
    frame, seen = drawn(key)
    heading, home = [spot.box for spot in seen.spots if spot.text == "Home"]
    assert seen.marked == (home,)
    checks = score(key, [seen])
    assert checks.passed
    [mark] = [item for item in checks.items() if item.code == "VT509"]
    assert (mark.about, mark.result, mark.element, mark.box) == ("Home", '"Home" marked, and no other tab', "Tabs", home)
    wrong = words(key, a_story()).replace('with "Home" chosen', 'with "Trips" chosen')
    frame, _ = standin.draw(standin.quoted(wrong), wrong)
    seen = StandInEye().see(frame)
    [mark] = score(key, [seen]).failures
    assert (mark.code, mark.about, mark.result) == ("VT509", "Home", 'marked "Trips"; "Home" is chosen')
    assert [item.code for item in score(key, [replace(seen, marked=None)]).items()] == ["VT501", "VT502", "VT502", "VT502"]


def test_a_date_picker_with_no_chosen_day_marks_none_and_a_reader_that_reports_no_marks_judges_no_mark():
    picked = key_of(vt.Text("Picked"))
    key = key_of(vt.DatePicker({date(2026, 12, 5): vt.Option("$219", to=picked.state),
                                date(2026, 12, 12): vt.Option("$189", to=picked.state)}))
    frame, seen = drawn(key)
    assert seen.marked == ()
    [mark] = [item for item in score(key, [seen]).items() if item.code == "VT509"]
    assert (mark.about, mark.result, mark.passed, mark.element) == ("DatePicker", "no day marked", True, "DatePicker")
    twelve = next(spot.box for spot in seen.spots if spot.text == "12")
    [mark] = [item for item in score(key, [replace(seen, marked=(twelve,))]).failures]
    assert (mark.code, mark.result) == ("VT509", 'marked "12"; no day is chosen')
    assert "VT509" not in [item.code for item in score(key, [replace(seen, marked=None)]).items()]


def test_vt504_judges_a_chart_whole_from_a_reader_that_reports_charts_and_leaves_its_lines_to_the_readers_that_do_not():
    key = key_of(vt.Heading("Flown"), vt.BarChart("Flights per month", {"Jan": 0, "Feb": 1, "Mar": 2}))
    frame, seen = drawn(key)
    chart = Chart("Flights per month", ("Jan", "Feb", "Mar"), (0.0, 1.0, 2.1))
    charted = Read("made-up", seen.spots, charts=(chart,))
    checks = score(key, [seen, charted])
    assert checks.passed
    assert [(reading.line, [one.reader for one in reading.seen]) for reading in checks.text] == [
        ("Flown", ["stand-in", "made-up"]), ("Flights per month", ["stand-in"]), ("Jan", ["stand-in"]),
        ("0", ["stand-in"]), ("Feb", ["stand-in"]), ("1", ["stand-in"]), ("Mar", ["stand-in"]), ("2", ["stand-in"])]
    [plotted] = [item for item in checks.items() if item.code == "VT504"]
    assert (plotted.about, plotted.result, plotted.element, plotted.box) == (
        "Flights per month", "3 bars, the title, every label and every value within 10%, by made-up", "BarChart", None)
    assert [item.code for item in score(key, [seen]).items()] == ["VT502"] * 8

    def off(*charts: Chart) -> list[str]:
        [item] = [item for item in score(key, [replace(charted, charts=charts)]).items() if item.code == "VT504"]
        assert not item.passed
        return item.result.split("; ")

    assert off(replace(chart, values=(0.0, 1.0, 2.3))) == ["Mar read 2.3, 2 in the data"]
    assert off(replace(chart, values=(0.5, 1.0, 2.0))) == ["Jan read 0.5, 0 in the data"]
    assert off(replace(chart, labels=("Jan", "Feb"), values=(0.0, 1.0))) == ["2 bars, 3 expected"]
    assert off(replace(chart, labels=("Jan", "Fed", "Mar"))) == ["labels read Jan, Fed, Mar"]
    assert off(replace(chart, title="Flights per nonth", values=(0.0, 1.0, 9.0))) == [
        'title read "Flights per nonth"', "Mar read 9, 2 in the data"]
    assert off() == ["no chart read"]


def test_two_charts_pair_with_what_a_reader_saw_by_their_titles_and_a_line_chart_counts_points():
    key = key_of(vt.BarChart("Flights", {"Jan": 1, "Feb": 2}), vt.LineChart("Miles", {"Jan": 100, "Feb": 300}))
    frame, seen = drawn(key)
    miles = Chart("Miles", ("Jan", "Feb"), (100.0, 290.0))
    flights = Chart("Flights", ("Jan", "Feb"), (1.0, 2.0))
    items = [item for item in score(key, [Read("made-up", seen.spots, charts=(miles, flights))]).items()
             if item.code == "VT504"]
    assert [(item.about, item.passed, item.element) for item in items] == [("Flights", True, "BarChart"),
                                                                            ("Miles", True, "LineChart")]
    [_, points] = [item for item in score(key, [Read("made-up", seen.spots, charts=(flights,))]).items()
                   if item.code == "VT504"]
    assert (points.about, points.result) == ("Miles", "no chart read")
    [short] = [item for item in score(key, [Read("made-up", seen.spots, charts=(flights, Chart("Miles", ("Jan",), (100.0,))))]).failures]
    assert short.result == "1 point, 2 expected"


def test_an_options_label_on_a_day_with_no_option_fails_vt502_as_the_date_pickers_and_is_not_an_invented_control():
    picked = key_of(vt.Text("Picked"))
    key = key_of(vt.DatePicker({date(2026, 12, 5): vt.Option("$219", to=picked.state),
                                date(2026, 12, 12): vt.Option("$1,019", to=picked.state)}))
    seen = Read("stand-in", spots("December 2026", "5", "$219", "12", "$1,019", "$240", "19", "Book",
                                  controls=("5", "12", "$240", "19", "Book")))
    checks = score(key, [seen])
    assert failed(checks) == [("VT502", "$240"), ("VT503", "19"), ("VT503", "Book")]
    [stray, *_] = checks.failures
    assert (stray.result, stray.element, stray.box) == ('a day with no option shows "$240" at 0,200 100x33', "DatePicker",
                                                        seen.spots[5].box)
    assert checks.rank(1)[1] == 2


def test_an_invented_control_names_its_reader_when_there_are_several():
    key = key_of(vt.Heading("Thanks"))
    first = Read("stand-in", spots("Thanks"))
    second = Read("second", spots("Thanks", "Cancel", controls=("Cancel",)))
    [item] = score(key, [first, second]).failures
    assert (item.code, item.about, item.element) == ("VT503", "Cancel", None)
    assert item.result == 'a control reading "Cancel" at 0,40 100x33, and no action has those words, by second'
    [item] = score(key, [second]).failures
    assert item.result == 'a control reading "Cancel" at 0,40 100x33, and no action has those words'


class Disagreeing(StandInEye):
    """A second reader, which reads the stand-in's boxes as the stand-in does but for the word Thanks."""

    name = "disagreeing"

    def see(self, frame, purse=Free()) -> Read:
        seen = super().see(frame)
        return dataclasses.replace(seen, reader=self.name, spots=tuple(
            dataclasses.replace(spot, text="Thank") if spot.text == "Thanks" else spot for spot in seen.spots))


def test_the_dailies_keep_each_readers_reading_and_show_both_when_the_readers_disagree(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    clean = lambda mode, prompt, seed: standin.Flaw.NONE
    monkeypatch.setitem(MODELS, "stand-in", Listing(lambda: StandIn(flaw=clean), (StandInEye, Disagreeing), limit=8,
                                                     kind=StandIn))
    assert cli(directory, "render", "--story", "chalk", "--takes", "1") == 1
    err = capsys.readouterr().err
    assert ('fail: 4. key thanks(Espresso)  VT502 Thanks: read "Thanks" by stand-in and "Thank" by disagreeing, CER 0.000 '
            "and 0.167") in err
    record = dailies.read(directory / "tapes" / "chalk")
    assert record["checks"] == "stand-in and disagreeing"
    assert [(failure["shot"], failure["code"], failure["about"], failure["element"]) for failure in record["failures"]] == [
        ("key thanks(Espresso)", "VT502", "Thanks", "Heading"), ("key thanks(Latte)", "VT502", "Thanks", "Heading")]
    first = record["failures"][0]
    assert [(reading["reader"], reading["text"], reading["cer"]) for reading in first["readings"]] == [
        ("stand-in", "Thanks", 0.0), ("disagreeing", "Thank", 1 / 6)]
    assert first["readings"][0]["box"] == first["crop_box"]
    assert first["next"]["story"] == "stories/chalk.toml line 15, elements.Heading"
    items = record["keys"][0]["items"]
    assert all("element" in item and "readings" in item for item in items)
    assert [(item["code"], item["element"]) for item in items][:3] == [("VT501", "List"), ("VT501", "List"),
                                                                        ("VT502", "Heading")]
    page = (directory / "tapes" / "chalk" / "dailies.html").read_text()
    assert ('<ul class="readings"><li>stand-in read &quot;Thanks&quot;</li><li>disagreeing read &quot;Thank&quot;</li>'
            "</ul>") in page
    assert page.count('<ul class="readings">') == 2
    assert "2 keys checked by stand-in and disagreeing" not in page and "5 keys checked by stand-in and disagreeing" in page
