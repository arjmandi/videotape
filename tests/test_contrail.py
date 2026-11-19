import json
import os
import urllib.request

import pytest

import conftest
from conftest import CONTRAIL, contrail_copy, planned, videotape
from videotape import claude, fal, project

PLAN = """\
Contrail 0.1.0: 11 scenes, 58 states, 58 keys of which 10 rehearsed, 102 moves, 150 shots

scene        states   moves out
home              1           4
search            1           7
not_found         1           1
no_flights        3           3
dates             3           9
results           9          36
flight           18          18
booked           18          18
my_trips          1           4
trip              2           0
profile           1           2

0 errors, 0 warnings
gemini-omni-flash-1.2: 150 shots, 150 to 600 calls, $65.92 to $263.70 at $0.0819/s plus $0.03 a call for the prompt, \
and 58 to 232 reads by claude-opus-5-5, at most $10.01 to $40.04, and 102 to 408 judgments by claude-opus-5-5, at most $12.47 to $49.87
"""
TODAY = "2026-12-01"
HOME = "SFO"
OTHER_TABS = 2


def counted_from_the_data() -> dict[str, tuple[int, int]]:
    """Each scene's states and moves out, counted from Contrail's data files by what its README says the app does."""
    airports, flights, trips = (json.loads((CONTRAIL / "data" / f"{name}.json").read_text())
                                for name in ("airports", "flights", "trips"))
    places = [airport["code"] for airport in airports if airport["code"] != HOME]
    served = {flight["destination"] for flight in flights}
    days = {place: {flight["day"] for flight in flights if flight["destination"] == place} for place in served}
    on_a_day = {(flight["destination"], flight["day"]) for flight in flights}
    upcoming = [trip for trip in trips if trip["day"] >= TODAY]
    search_bar = next_trip = search_again = book = done = 1
    return {
        "home": (1, search_bar + next_trip + OTHER_TABS),
        "search": (1, len(places) + 1),
        "not_found": (1, search_again),
        "no_flights": (len(places) - len(served), (len(places) - len(served)) * search_again),
        "dates": (len(served), sum(len(days[place]) for place in served)),
        "results": (len(on_a_day), sum(len(days[place]) - 1 + sum((flight["destination"], flight["day"]) == (place, day)
                                                                    for flight in flights) for place, day in on_a_day)),
        "flight": (len(flights), len(flights) * book),
        "booked": (len(flights), len(flights) * done),
        "my_trips": (1, len(upcoming) + OTHER_TABS),
        "trip": (len(upcoming), 0),
        "profile": (1, OTHER_TABS),
    }


def table(text: str) -> dict[str, tuple[int, int]]:
    rows = (line.split() for line in text.splitlines()[3:-3])
    return {name: (int(states), int(moves)) for name, states, moves in rows}


def test_plan_prints_contrails_scenes_states_and_moves():
    result = videotape(CONTRAIL, "plan")
    assert (result.stdout, result.stderr, result.returncode) == (PLAN, "", 0)


def test_the_data_alone_gives_every_number_the_plan_prints():
    counted = counted_from_the_data()
    assert counted == table(PLAN)
    states, moves = sum(states for states, _ in counted.values()), sum(moves for _, moves in counted.values())
    rehearsed = len(counted) - 1
    assert PLAN.startswith(f"Contrail 0.1.0: {len(counted)} scenes, {states} states, {states} keys of which {rehearsed} "
                           f"rehearsed, {moves} moves, {states + moves - rehearsed} shots\n")
    assert [name for name, (_, moves) in counted.items() if not moves] == ["trip"]


def test_the_two_trips_are_the_only_states_without_actions():
    assert [key.state.name for key in planned(CONTRAIL).keys if not key.actions] == [
        "trip(CT 100, 2026-12-18)", "trip(CT 500, 2027-01-08)"]


def test_booking_the_morning_flight_to_seattle_lands_back_on_home():
    moves = {(move.start.name, move.label): move.land.name for move in planned(CONTRAIL).moves}
    state = "home()"
    for label in ("Where to?", "Seattle (SEA)", "Saturday, December 12, $89",
                  "8:15 AM to 10:25 AM, 2h 10m, Nonstop, $89", "Book for $89", "Done"):
        state = moves[(state, label)]
    assert state == "home()"
    assert moves[("search()", "Where to?")] == "not_found()"
    assert moves[("search()", "Boston (BOS)")] == "no_flights(BOS)"


def test_contrails_screenplay_stays_under_200_lines():
    assert len((CONTRAIL / "contrail" / "screenplay.py").read_text().splitlines()) < 200


def test_a_copy_of_contrail_leaves_the_api_keys_in_its_env_behind(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text((CONTRAIL / "pyproject.toml").read_text())
    (source / ".env").write_text("FAL_KEY=fal-not-a-real-key\nANTHROPIC_API_KEY=sk-ant-not-a-real-key\n")
    monkeypatch.setattr(conftest, "CONTRAIL", source)
    for key in ("FAL_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    project.find(contrail_copy(tmp_path / "copy"))
    assert {key: os.environ.get(key) for key in ("FAL_KEY", "ANTHROPIC_API_KEY")} == {
        "FAL_KEY": None, "ANTHROPIC_API_KEY": None}
    project.find(source)
    assert {key: os.environ.get(key) for key in ("FAL_KEY", "ANTHROPIC_API_KEY")} == {
        "FAL_KEY": "fal-not-a-real-key", "ANTHROPIC_API_KEY": "sk-ant-not-a-real-key"}


def test_no_test_reaches_fal_or_claude_so_none_pays_with_the_keys_it_finds():
    for send in (fal._urlopen, claude._urlopen):
        with pytest.raises(AssertionError, match="^a test reached for the network: http://127.0.0.1:9/$"):
            send(urllib.request.Request("http://127.0.0.1:9/"))
