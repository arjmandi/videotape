"""The checks over every reader of a key's picture: what each reader reports, what the checks judge from it, and what
the record keeps. The readers here are the stand-in's own and readers made up for a test, which report what they are
given, so no test loads a model or sends a request."""

import dataclasses
import json
import time
from collections import Counter
from dataclasses import replace
from datetime import date

import pytest

import videotape as vt
from conftest import CONTRAIL, FIXTURES, a_story, copy_of, planned, words
from videotape import dailies, standin
from videotape.checks import MAX_SCENE, Chart, Cut, Dissolve, Free, MoveChecks, Read, Spot, dissolved, readings, score
from videotape.frames import Box
from videotape.layout import BAR, Compared, Layout
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


def test_a_period_at_the_end_of_a_line_fails_vt502_unless_the_line_has_none_and_another_reader_reads_it_exactly():
    key = key_of(vt.Text("7h 10m, 1 stop"))
    period = Read("qwen", spots("7h 10m, 1 stop."))
    assert failed(score(key, [period, Read("claude", spots("7h 10m, 1 stop"))])) == []
    assert failed(score(key, [period, replace(period, reader="claude")])) == [("VT502", "7h 10m, 1 stop")]
    assert failed(score(key, [period])) == [("VT502", "7h 10m, 1 stop")]
    latte = key_of(vt.Text("One Latte coming up."))
    assert failed(score(latte, [Read("qwen", spots("One Latte coming up..")),
                                Read("claude", spots("One Latte coming up."))])) == [("VT502", "One Latte coming up.")]


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


def test_vt505_judges_a_variants_layout_distances_by_the_bar_the_marks_set():
    frame, seen = drawn(key_of(vt.Heading("Thanks"), vt.Button("Done", to=key_of(vt.Text("Bye")).state)))
    checks = score(key_of(vt.Heading("Thanks"), vt.Button("Done", to=key_of(vt.Text("Bye")).state)), [seen])
    assert checks.layout is None and "VT505" not in {item.code for item in checks.items()}
    thanks, done = (spot.box for spot in seen.spots)
    assert Counter(checks.boxes) == {done: 4, thanks: 2}
    close = replace(checks, layout=Compared(Layout(0.1525, 0.9, 0.86), BAR))
    assert [(item.code, item.about, item.passed, item.result, item.box) for item in close.items()][-1] == (
        "VT505", "layout against the base", True,
        "shading 0.1525, edges 0.9000, 86% of the picture compared; shading under the threshold of 0.1525", None)
    far = replace(checks, layout=Compared(Layout(0.207, 0.812, 0.86), BAR))
    assert far.failures[-1].result == ("shading 0.2070, edges 0.8120, 86% of the picture compared; shading over the "
                                       "threshold of 0.1525")
    assert far.rank(2) == checks.rank(2) and not far.passed


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
    row = [("5", 24), ("$219", 60), ("12", 180), ("$1,019", 240), ("19", 420), ("$240", 480)]
    seen = Read("stand-in", (Spot("December 2026", Box(24, 24, 243, 33), False),
                             *(Spot(text, Box(x, 66, 27 * len(text), 33), text != "$219" and text != "$1,019")
                               for text, x in row), Spot("Book", Box(24, 300, 120, 33), True)))
    checks = score(key, [seen])
    assert failed(checks) == [("VT502", "$240"), ("VT503", "Book")]
    [stray, *_] = checks.failures
    assert (stray.result, stray.element, stray.box) == ('a day with no option shows "$240" at 480,66 108x33',
                                                        "DatePicker", seen.spots[6].box)
    assert checks.rank(1)[1] == 1


JFK = {date(2026, 12, 11): "$199", date(2026, 12, 12): "$179", date(2026, 12, 13): "$229"}


def month(fares: dict[int, str], joined: bool = False) -> tuple[Spot, ...]:
    """A December 2026 calendar as a reader reports it: every day a control in a grid of 7 a row, Sunday first, and
    each label under its day, or read with it as one spot, "14 $199"."""
    drawn = [Spot("December 2026", Box(60, 0, 240, 30), False)]
    for day in range(1, 32):
        at = Box(60 * ((day + 1) % 7), 40 + 60 * ((day + 1) // 7), 40, 20)
        label = fares.get(day)
        if label and joined:
            drawn.append(Spot(f"{day} {label}", Box(at.x, at.y, at.w, 48), True))
        else:
            drawn.append(Spot(str(day), at, True))
            if label:
                drawn.append(Spot(label, Box(at.x, at.y + 26, at.w, 20), True))
    return tuple(drawn)


def jfk() -> Key:
    picked = key_of(vt.Text("Picked"))
    return key_of(vt.DatePicker({day: vt.Option(fare, to=picked.state) for day, fare in JFK.items()}))


@pytest.mark.parametrize("joined", [False, True], ids=["under", "joined"])
def test_a_month_drawn_right_passes_and_its_days_without_flights_are_not_invented_controls(joined):
    checks = score(jfk(), [Read("made-up", month({11: "$199", 12: "$179", 13: "$229"}, joined))])
    assert checks.passed, failed(checks)
    assert checks.invented == ()


@pytest.mark.parametrize("joined", [False, True], ids=["under", "joined"])
def test_a_fare_on_a_day_without_flights_fails_vt502_read_under_the_day_or_with_it(joined):
    seen = Read("made-up", month({11: "$199", 12: "$179", 13: "$229", 14: "$199"}, joined))
    assert failed(score(jfk(), [seen])) == [("VT502", "$199")]
    [stray] = score(jfk(), [seen]).failures
    assert stray.result.startswith('a day with no option shows "$199"') and stray.element == "DatePicker"


def test_a_fare_is_judged_on_the_day_it_sits_on_so_fares_drawn_on_each_others_days_fail():
    seen = Read("made-up", month({11: "$179", 12: "$199", 13: "$229"}))
    assert failed(score(jfk(), [seen])) == [("VT502", "$199"), ("VT502", "$179")]
    [eleven, _] = score(jfk(), [seen]).failures
    assert eleven.result == 'read "$179", CER 0.250'


def test_a_line_read_in_two_spots_that_follow_each_other_is_read_whole():
    key = key_of(vt.Text("Pick a day. Each shows the lowest one-way fare."),
                 vt.Text("8:15 AM to 10:25 AM"), vt.Text("Departs 8:15 AM. Confirmation B5C25E."))
    seen = Read("made-up", (
        Spot("Pick a day. Each shows the", Box(498, 130, 280, 34), False),
        Spot("lowest one-way fare.", Box(528, 166, 212, 34), False),
        Spot("8:15 AM", Box(291, 273, 100, 30), False),
        Spot("to 10:25 AM", Box(405, 283, 122, 28), False),
        Spot("Confirmation B5C25E.", Box(522, 180, 268, 92), False),
        Spot("Departs 8:15 AM.", Box(364, 250, 156, 68), False)))
    checks = score(key, [seen])
    assert checks.passed, failed(checks)
    assert checks.text[0].box == Box(498, 130, 280, 70)


def test_two_spots_that_do_not_follow_each_other_are_not_read_as_one_line():
    key = key_of(vt.Text("8:15 AM to 10:25 AM"))
    apart = Read("made-up", (Spot("8:15 AM", Box(0, 0, 100, 30), False), Spot("to 10:25 AM", Box(600, 300, 122, 28), False)))
    assert failed(score(key, [apart])) == [("VT502", "8:15 AM to 10:25 AM")]


def test_a_spot_read_across_a_line_break_is_a_line_each():
    key = key_of(vt.Text("Sat 12"), vt.Text("$89"))
    seen = Read("made-up", (Spot("Sat 12\n$89", Box(523, 296, 143, 185), True),))
    checks = score(key, [seen])
    assert checks.passed, failed(checks)
    assert [reading.box for reading in checks.text] == [Box(523, 296, 143, 92), Box(523, 388, 143, 92)]


def test_an_action_split_across_a_list_rows_columns_is_found():
    there = key_of(vt.Text("There"))
    key = key_of(vt.List([vt.Row("8:15 AM to 10:25 AM", "2h 10m, Nonstop", "$89", to=there.state)], "Flights"))
    seen = Read("made-up", (Spot("Flights", Box(291, 230, 100, 30), False), Spot("8:15 AM", Box(291, 273, 100, 30), True),
                            Spot("to 10:25 AM", Box(405, 283, 122, 28), True),
                            Spot("2h 10m, Nonstop", Box(580, 290, 134, 24), False), Spot("$89", Box(768, 301, 26, 20), False)))
    checks = score(key, [seen])
    assert checks.passed, failed(checks)
    assert checks.hotspots == {"8:15 AM to 10:25 AM, 2h 10m, Nonstop, $89": Box(291, 273, 236, 38)}


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
        ("key thanks(Espresso)", "VT502", "Thanks", "Heading"),
        ("key thanks(Latte) from thanks(Espresso)", "VT502", "Thanks", "Heading")]
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


def jfk_beside(*elements) -> Key:
    picked = key_of(vt.Text("Picked"))
    return key_of(*elements, vt.DatePicker({day: vt.Option(fare, to=picked.state) for day, fare in JFK.items()}))


def test_a_line_is_not_read_whole_from_a_plain_spot_and_a_control():
    seen = Read("made-up", (Spot("Delete", Box(20, 20, 100, 30), False), Spot("account", Box(20, 60, 100, 30), True)))
    assert failed(score(key_of(vt.Text("Delete account")), [seen])) == [("VT502", "Delete account")]


def test_two_lines_each_read_in_two_spots_are_both_read_whatever_order_the_reader_gave_the_spots():
    key = key_of(vt.Heading("Welcome back"), vt.Text("back soon"))
    seen = Read("made-up", (Spot("Welcome", Box(0, 0, 100, 30), False), Spot("back", Box(0, 40, 50, 25), False),
                            Spot("back", Box(110, 0, 40, 30), False), Spot("soon", Box(60, 40, 40, 25), False)))
    checks = score(key, [seen])
    assert checks.passed, failed(checks)


def test_a_calendars_label_is_not_read_again_for_another_line():
    seen = Read("made-up", month({11: "$199", 12: "$179", 13: "$229"}))
    assert failed(score(jfk_beside(vt.Text("$199")), [seen])) == [("VT502", "$199")]


def test_a_day_number_away_from_the_calendar_is_an_invented_control():
    seen = Read("made-up", (*month({11: "$199", 12: "$179", 13: "$229"}), Spot("7", Box(700, 600, 40, 30), True)))
    assert failed(score(jfk(), [seen])) == [("VT503", "7")]


def test_a_day_drawn_again_away_from_the_calendar_does_not_lend_its_fare_to_the_calendars_day():
    seen = Read("made-up", (*month({12: "$179", 13: "$229"}), Spot("11", Box(700, 600, 40, 20), True),
                            Spot("$199", Box(700, 626, 40, 20), True)))
    assert ("VT502", "$199") in failed(score(jfk(), [seen]))


def test_a_day_read_with_its_fare_across_a_line_break_keeps_its_mark():
    eleven = Box(300, 100, 40, 48)
    spots = tuple(Spot("11\n$199", eleven, True) if spot.text == "11" else spot
                  for spot in month({12: "$179", 13: "$229"}))
    [mark] = [item for item in score(jfk(), [Read("made-up", spots, marked=(eleven,))]).items() if item.code == "VT509"]
    assert (mark.passed, mark.result) == (False, 'marked "11"; no day is chosen')


def test_a_date_strips_fare_is_read_from_the_day_it_sits_on():
    picked = key_of(vt.Text("Picked"))
    key = key_of(vt.DateStrip({date(2026, 12, 11): vt.Option("$99", to=picked.state),
                               date(2026, 12, 12): vt.Option("$89", to=picked.state),
                               date(2026, 12, 13): vt.Option("$109", to=picked.state)}))
    # Claude's read of wan3.0's take 1 of results(SEA, 2026-12-12): $99 is drawn under 5:40 AM, and 11 under Fri 11.
    seen = Read("claude-opus-5-5", (Spot("5:40 AM\n$99", Box(196, 362, 96, 148), True),
                                     Spot("Fri 11\n11", Box(292, 346, 110, 154), True),
                                     Spot("Sat 12\n$89", Box(523, 296, 143, 185), True),
                                     Spot("Sun 13\n$109", Box(825, 246, 178, 200), True)))
    assert ("VT502", "$99") in failed(score(key, [seen]))
    right = Read("claude-opus-5-5", (Spot("Fri 11\n$99", Box(292, 346, 110, 154), True),
                                      Spot("Sat 12\n$89", Box(523, 296, 143, 185), True),
                                      Spot("Sun 13\n$109", Box(825, 246, 178, 200), True)))
    assert score(key, [right]).passed, failed(score(key, [right]))


def test_a_day_drawn_twice_is_misread_as_both_of_its_readings():
    picked = key_of(vt.Text("Picked"))
    key = key_of(vt.DateStrip({date(2026, 12, 11): vt.Option("$99", to=picked.state),
                               date(2026, 12, 12): vt.Option("$89", to=picked.state)}))
    seen = Read("made-up", (Spot("Fri 11\n$99", Box(200, 250, 180, 140), True),
                            Spot("Fri 11\n$99", Box(390, 250, 180, 140), True),
                            Spot("Sat 12\n$89", Box(580, 250, 180, 140), True)))
    assert [(item.code, item.about, item.result) for item in score(key, [seen]).failures] == [
        ("VT502", "Fri 11", 'read "Fri 11 / Fri 11", CER 1.500'), ("VT502", "$99", 'read "$99 / $99", CER 2.000')]


DRAWN = {11: "$199", 12: "$179", 13: "$229"}


@pytest.mark.parametrize("element, spot", [
    (vt.Heading("2"), Spot("2", Box(60, 10, 40, 20), False)),
    (vt.Text("$89"), Spot("$89", Box(120, 380, 40, 20), False)),
], ids=["a number above it", "a fare below it"])
def test_text_near_a_calendar_is_read_as_its_own_line(element, spot):
    checks = score(jfk_beside(element), [Read("made-up", (*month(DRAWN), spot))])
    assert checks.passed, failed(checks)


def test_a_number_beside_a_calendars_row_is_an_invented_control():
    seen = Read("made-up", (*month(DRAWN), Spot("7", Box(420, 100, 40, 20), True)))
    assert failed(score(jfk(), [seen])) == [("VT503", "7")]


def test_a_month_whose_rows_are_far_apart_is_read_whole():
    stretched = tuple(replace(spot, box=replace(spot.box, y=spot.box.y + 60 * ((spot.box.y - 40) // 60)))
                      for spot in month(DRAWN))
    checks = score(jfk(), [Read("made-up", stretched)])
    assert checks.passed, failed(checks)
    assert checks.invented == ()


def test_lines_of_the_same_words_read_in_two_spots_each_are_paired_quickly_however_many():
    rows = [(Spot("2h 10m,", Box(0, 40 * row, 80, 30), False), Spot("Nonstop", Box(90, 40 * row, 80, 30), False))
            for row in range(9)]
    others = [Spot(f"x{number}", Box(600, 40 * number, 40, 30), False) for number in range(22)]
    started = time.perf_counter()
    paired = readings("made-up", ["2h 10m, Nonstop"] * 10, [spot for row in rows for spot in row] + others)
    assert time.perf_counter() - started < 1
    assert sum(seen.cer == 0 for seen, _ in paired) == 9


def test_a_label_within_a_days_cell_reads_as_its_label_however_far_down_the_cell_draws_it():
    """A fare-shaped text in a day's cell is that day's fare, as a person reads it: the fare of a day with no option
    strays. Its cell is a row's step deep, measured from the read."""
    lower = tuple(replace(spot, box=replace(spot.box, y=spot.box.y + 19)) if spot.text.startswith("$") else spot
                  for spot in month(DRAWN))
    assert score(jfk(), [Read("made-up", lower)]).passed
    in_a_cell = Read("made-up", (*month(DRAWN), Spot("$89", Box(120, 326, 40, 20), False)))
    assert failed(score(jfk_beside(vt.Text("$89")), [in_a_cell])) == [("VT502", "$89"), ("VT502", "$89")]


def jan_31() -> Key:
    picked = key_of(vt.Text("Picked"))
    return key_of(vt.DatePicker({date(2027, 1, 31): vt.Option("$99", to=picked.state)}))


def test_a_month_whose_last_row_holds_one_day_reads_that_day():
    january = [Spot(str(day), Box(60 * ((day + 4) % 7), 40 + 60 * ((day + 4) // 7), 40, 20), True) for day in range(1, 32)]
    thirty_first = january[-1].box
    seen = Read("made-up", (Spot("January 2027", Box(60, 0, 240, 30), False), *january,
                            Spot("$99", Box(thirty_first.x, thirty_first.y + 26, 40, 20), True)))
    checks = score(jan_31(), [seen])
    assert checks.passed, failed(checks)


def test_a_month_seen_at_an_angle_reads_whole():
    sheared = tuple(replace(spot, box=replace(spot.box, x=spot.box.x + 24 * ((spot.box.y - 40) // 60)))
                    for spot in month(DRAWN))
    checks = score(jfk(), [Read("made-up", sheared)])
    assert checks.passed, failed(checks)
    assert checks.invented == ()


def test_the_stand_ins_date_picker_of_one_day_reads_it():
    picked = key_of(vt.Text("Picked"))
    key = key_of(vt.DatePicker({date(2026, 12, 11): vt.Option("$199", to=picked.state)}))
    frame, seen = drawn(key)
    assert score(key, [seen]).passed, failed(score(key, [seen]))


@pytest.mark.parametrize("words, control, expected", [
    ("Sat 12", False, []), ("Mon 14", True, [("VT503", "Mon 14")])], ids=["its own line", "an invented control"])
def test_a_weekday_and_day_away_from_a_strip_is_not_the_strips(words, control, expected):
    picked = key_of(vt.Text("Picked"))
    strip = vt.DateStrip({date(2026, 12, 11): vt.Option("$99", to=picked.state),
                          date(2026, 12, 12): vt.Option("$89", to=picked.state)})
    key = key_of(strip, vt.Text("Sat 12")) if not control else key_of(strip)
    seen = Read("made-up", (Spot("Fri 11\n$99", Box(200, 250, 180, 140), True),
                            Spot("Sat 12\n$89", Box(390, 250, 180, 140), True), Spot(words, Box(0, 400, 100, 20), control)))
    assert failed(score(key, [seen])) == expected


def test_a_search_for_joins_reads_every_line_it_can_when_lines_share_spots():
    spots = [Spot("Flight", Box(0, 40, 80, 30), False), Spot("details", Box(90, 40, 80, 30), False),
             Spot("time", Box(0, 80, 80, 30), False), Spot("Trip", Box(90, 0, 80, 30), False),
             *(Spot("Flight", Box(0, 200 + 20 * row, 80, 30), False) for row in range(1, 12)),
             *(Spot("details", Box(90, 200 + 20 * row, 80, 30), False) for row in range(1, 11))]
    lines = ["Flight details"] * 12 + ["Flight time", "Trip details"]
    paired = readings("made-up", lines, spots)
    assert [seen.cer == 0 for seen, _ in paired][-2:] == [True, True]
    assert sum(seen.cer == 0 for seen, _ in paired) == 12


def test_a_month_sheared_by_half_a_column_reads_every_day_of_its_grid():
    sheared = tuple(replace(spot, box=replace(spot.box, x=spot.box.x + round((spot.box.y - 40) / 2)))
                    for spot in month(DRAWN))
    checks = score(jfk(), [Read("made-up", sheared)])
    assert checks.passed, failed(checks)


def test_a_strip_that_slopes_more_than_its_lettering_is_tall_reads_every_day():
    picked = key_of(vt.Text("Picked"))
    key = key_of(vt.DateStrip({date(2026, 12, 11): vt.Option("$99", to=picked.state),
                               date(2026, 12, 12): vt.Option("$89", to=picked.state),
                               date(2026, 12, 13): vt.Option("$109", to=picked.state)}))
    days = [("Fri 11", "$99", 100, 100), ("Sat 12", "$89", 300, 135), ("Sun 13", "$109", 500, 180)]
    seen = Read("made-up", tuple(spot for day, fare, x, y in days for spot in (
        Spot(day, Box(x, y, 70, 20), True), Spot(fare, Box(x, y + 26, 70, 20), True))))
    checks = score(key, [seen])
    assert checks.passed, failed(checks)


def test_a_day_without_an_option_drawn_marked_fails_vt509():
    drawn_month = month(DRAWN)
    fourteen = next(spot.box for spot in drawn_month if spot.text == "14")
    [mark] = [item for item in score(jfk(), [Read("made-up", drawn_month, marked=(fourteen,))]).items()
              if item.code == "VT509"]
    assert (mark.passed, mark.result) == (False, 'marked "14"; no day is chosen')


def test_a_sparse_month_with_a_misread_grey_day_keeps_its_option_days():
    kept = {2, 4, 7, 11, 12, 13, 21, 25, 27}
    seen = Read("made-up", tuple(replace(spot, text="14") if spot.text == "2" else spot for spot in month(DRAWN)
                                 if not spot.text.isdigit() or int(spot.text) in kept))
    assert failed(score(jfk(), [seen])) == []


def test_a_month_whose_rows_are_far_apart_and_sheared_reads_every_day():
    stretched = tuple(replace(spot, box=Box(50 * ((day + 1) % 7) + 25 * ((day + 1) // 7) + (spot.box.x % 60),
                                            40 + 150 * ((day + 1) // 7) + (spot.box.y - 40) % 60, spot.box.w, spot.box.h))
                      if (day := _day_of(spot)) else spot for spot in month(DRAWN))
    checks = score(jfk(), [Read("made-up", stretched)])
    assert checks.passed, failed(checks)


def _day_of(spot: Spot) -> int | None:
    """The day of month() a spot is, its number or the label under it, from where month() put it."""
    if spot.text == "December 2026":
        return None
    column, row = spot.box.x // 60, (spot.box.y - 40) // 60
    return row * 7 + column - 1


def test_a_weekday_and_day_tile_off_the_strips_line_is_an_invented_control():
    picked = key_of(vt.Text("Picked"))
    key = key_of(vt.DateStrip({date(2026, 12, 11): vt.Option("$99", to=picked.state),
                               date(2026, 12, 12): vt.Option("$89", to=picked.state),
                               date(2026, 12, 13): vt.Option("$109", to=picked.state)}))
    days = [("Fri 11", "$99", 100), ("Sat 12", "$89", 300), ("Sun 13", "$109", 500)]
    seen = Read("made-up", (*(spot for day, fare, x in days for spot in (Spot(day, Box(x, 100, 70, 20), True),
                                                                          Spot(fare, Box(x, 126, 70, 20), True))),
                            Spot("Mon 14", Box(700, 250, 70, 20), True)))
    assert failed(score(key, [seen])) == [("VT503", "Mon 14")]


def recorded(name: str) -> list[Read]:
    return [Read(one["reader"], tuple(Spot(spot["text"], Box(**spot["box"]), spot["control"]) for spot in one["spots"]),
                 None if one["marked"] is None else tuple(Box(**box) for box in one["marked"]),
                 None if one["charts"] is None else ())
            for one in json.loads((FIXTURES / "recorded" / "reads" / f"{name}.json").read_text())]


def test_a_strip_whose_weekdays_the_readers_read_apart_from_their_days_reads_whole():
    """Both readers of gemini-omni-flash-1.2's take 2 of results(SEA, 2026-12-12) in the paid run read each tile as
    "Fri", "11" and "$99": Qwen one under another, Claude all in the tile's box, with Saturday's marked."""
    key = next(key for key in planned(CONTRAIL).keys if key.state.name == "results(SEA, 2026-12-12)")
    checks = score(key, recorded("gemini-posters-results-take-2"))
    assert [(item.code, item.about) for item in checks.items() if item.element == "DateStrip" and not item.passed] == []
    assert checks.invented == ()


def test_a_period_qwen_adds_to_a_line_claude_reads_exactly_passes_vt502():
    key = next(key for key in planned(CONTRAIL).keys if key.state.name == "flight(CT 104, 2026-12-13)")
    [item] = [item for item in score(key, recorded("wan3-terminal-flight-ct104-take-2")).items()
              if item.about == "1:30 PM to 11:40 PM, 7h 10m, 1 stop"]
    assert [(seen.reader, seen.text) for seen in item.readings] == [
        ("qwen3-vl-8b", "1:30 PM to 11:40 PM, 7h 10m, 1 stop."),
        ("claude-opus-5-5", "1:30 PM to 11:40 PM, 7h 10m, 1 stop")]
    assert (item.code, item.passed) == ("VT502", True)


def test_a_move_cuts_at_the_frame_whose_scene_score_is_over_the_threshold():
    cut = Cut((0.0, 0.04, 0.35, 0.02))
    assert (cut.top, cut.passed) == ((2, 0.35), False)
    item = cut.item()
    assert (item.code, item.about, item.result, item.passed, item.box) == (
        "VT506", "frame 2", f"scene score 0.350, over the threshold of {MAX_SCENE}", False, None)
    smooth = Cut((0.0, 0.1, 0.187, 0.12))
    assert smooth.passed and smooth.item().about == "frame 2" and "0.187, under the threshold" in smooth.item().result
    assert Cut((0.0,)).passed and Cut(()).passed
    checks = MoveChecks(0.01, 0.02, cut=cut)
    assert [(item.code, item.passed) for item in checks.items()] == [("VT508", True), ("VT508", True), ("VT506", False)]
    assert not checks.passed and [item.code for item in checks.failures] == ["VT506"]
    assert MoveChecks(0.01, 0.02).items()[-1].code == "VT508"


def test_a_move_dissolves_when_any_judged_frame_shows_two_pictures_overlaid():
    at = (0, 21, 43, 64, 85, 106, 128, 149)
    seen = ("the shop door",) * 2 + ("the door fading into a form",) * 2 + ("the form",) * 4
    judged = Dissolve("claude-opus-5-5", at, (False, False, True, True, False, False, False, False), seen)
    assert not judged.passed and dissolved(judged.overlaid)
    item = judged.item()
    assert (item.code, item.about, item.passed) == ("VT507", "frames 43 and 64", False)
    assert item.result == "2 of 8 frames across the move show two pictures overlaid, by claude-opus-5-5"
    one = Dissolve("stand-in", at, (False,) * 5 + (True,) + (False,) * 2, seen)
    assert one.item().about == "frame 106" and one.item().result.startswith("1 of 8 frames")
    clean = Dissolve("claude-opus-5-5", at, (False,) * 8, seen)
    assert clean.passed and not dissolved(clean.overlaid)
    assert (clean.item().about, clean.item().result) == (
        "no frame", "none of 8 frames across the move shows two pictures overlaid, by claude-opus-5-5")
    checks = MoveChecks(0.3, 0.01, dissolve=judged)
    assert [(item.code, item.about, item.passed) for item in checks.items()] == [
        ("VT508", "start", False), ("VT508", "end", True), ("VT507", "frames 43 and 64", False)]
    assert checks.rank(2) == (0.31, 2)
