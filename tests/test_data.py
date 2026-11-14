import dataclasses
import runpy
from datetime import date, time
from pathlib import Path

import pytest

import videotape as vt
from videotape.errors import shown

HERE = shown(__file__)

FLIGHT = '''from datetime import date, time

import videotape as vt


class Flight(vt.Record, key=("number", "day")):
    number: str
    day: date
    departs: time
    fare: int


flights = vt.table(Flight, "data/flights.json")
'''
ROWS = '''[
  {"number": "CT 100", "day": "2026-12-11", "departs": "07:05", "fare": 219},
  {"number": "CT 100", "day": "2026-12-12", "departs": "07:05", "fare": 189}
]
'''


def load(project: Path, source: str = FLIGHT, rows: str | None = ROWS, module: str = "app.py") -> dict:
    """Run a module in a project whose data/flights.json holds these rows, and return what it defines."""
    (project / "pyproject.toml").write_text('[project]\nname = "app"\n')
    if rows is not None:
        (project / "data").mkdir(exist_ok=True)
        (project / "data" / "flights.json").write_text(rows)
    path = project / module
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return runpy.run_path(str(path))


def rejected(project: Path, monkeypatch, source: str = FLIGHT, rows: str | None = ROWS) -> vt.ScreenplayError:
    monkeypatch.chdir(project)
    with pytest.raises(vt.ScreenplayError) as raised:
        load(project, source, rows)
    return raised.value


class Drink(vt.Record, key="name"):
    name: str
    price: int
    size: str


LATTE, MOCHA, TEA, COCOA = Drink("Latte", 5, "tall"), Drink("Mocha", 6, "tall"), Drink("Tea", 3, "short"), Drink("Cocoa", 5, "short")
DRINKS = vt.Table(Drink, [LATTE, MOCHA, TEA, COCOA], "drinks.json")


def test_a_table_loads_typed_records_with_dates_and_times_read_from_text(tmp_path):
    defined = load(tmp_path)
    first, second = defined["flights"]
    assert (first.number, first.day, first.departs, first.fare) == ("CT 100", date(2026, 12, 11), time(7, 5), 219)
    assert second == defined["Flight"]("CT 100", date(2026, 12, 12), time(7, 5), 189)


def test_a_record_is_frozen_and_can_name_a_state():
    with pytest.raises(dataclasses.FrozenInstanceError):
        LATTE.price = 4
    assert {LATTE: "a key"}[Drink("Latte", 5, "tall")] == "a key"


def test_one_loads_a_single_record(tmp_path):
    source = ('import videotape as vt\n\n\nclass Traveler(vt.Record):\n    name: str\n    miles: int\n\n\n'
              'traveler = vt.one(Traveler, "data/flights.json")\n')
    traveler = load(tmp_path, source, '{"name": "Alex Rivera", "miles": 48250}\n')["traveler"]
    assert (traveler.name, traveler.miles) == ("Alex Rivera", 48250)


def test_a_path_is_relative_to_the_project_wherever_the_module_is(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path.parent)
    assert len(list(load(tmp_path, module="shop/models/tables.py")["flights"])) == 2


def test_where_keeps_the_rows_that_match_every_field_or_pass_a_test():
    assert list(DRINKS.where(size="tall")) == [LATTE, MOCHA]
    assert list(DRINKS.where(size="short", price=5)) == [COCOA]
    assert list(DRINKS.where(lambda drink: drink.price > 4)) == [LATTE, MOCHA, COCOA]
    assert list(DRINKS.where(lambda drink: drink.price > 4, size="tall")) == [LATTE, MOCHA]
    assert list(DRINKS.where(size="huge")) == []


def test_order_by_sorts_by_a_field_and_keeps_ties_in_order():
    assert list(DRINKS.order_by("price")) == [TEA, LATTE, COCOA, MOCHA]
    assert list(DRINKS.order_by("price", descending=True)) == [MOCHA, LATTE, COCOA, TEA]
    assert list(DRINKS.order_by("name")) == [COCOA, LATTE, MOCHA, TEA]


def test_limit_first_get_and_count():
    assert list(DRINKS.limit(2)) == [LATTE, MOCHA]
    assert list(DRINKS.limit(9)) == [LATTE, MOCHA, TEA, COCOA]
    assert DRINKS.order_by("price").first() == TEA
    assert DRINKS.get(name="Mocha") == MOCHA
    assert DRINKS.get(size="short", price=3) == TEA
    assert (DRINKS.count(), DRINKS.where(size="tall").count(), DRINKS.where(size="huge").count()) == (4, 2, 0)


def test_distinct_is_sorted_and_min_is_the_least():
    assert DRINKS.distinct("price") == [3, 5, 6]
    assert DRINKS.distinct("size") == ["short", "tall"]
    assert DRINKS.min("price") == 3
    assert DRINKS.where(size="tall").min("name") == "Latte"


def test_groups_count_and_sum_as_dictionaries():
    by_size = DRINKS.group_by(lambda drink: drink.size)
    assert by_size.count() == {"tall": 2, "short": 2}
    assert by_size.sum("price") == {"tall": 11, "short": 8}
    assert DRINKS.group_by(lambda drink: drink.price > 4).count() == {True: 3, False: 1}


def test_a_query_leaves_its_table_as_it_was():
    DRINKS.where(size="tall").order_by("price", descending=True).limit(1)
    assert list(DRINKS) == [LATTE, MOCHA, TEA, COCOA]


def test_a_missing_data_file_is_vt205_at_the_line_that_loads_it(tmp_path, monkeypatch):
    error = rejected(tmp_path, monkeypatch, rows=None)
    assert (error.code, error.place) == ("VT205", "app.py:13")
    assert error.message == "no data file at data/flights.json"
    assert error.fix == 'create it, or correct the path; "data/flights.json" is relative to the folder of pyproject.toml'


@pytest.mark.parametrize("path", ["flights.json", "../data/flights.json", "data/../flights.json", "/data/flights.json",
                                  "records/flights.json"])
def test_a_path_outside_data_is_vt205_at_the_line_that_loads_it(tmp_path, monkeypatch, path):
    error = rejected(tmp_path, monkeypatch, FLIGHT.replace("data/flights.json", path))
    assert (error.code, error.place, error.message) == ("VT205", "app.py:13", f'"{path}" is not under data/')
    assert error.fix == "keep every data file under data/ in the project, as in data/flights.json"


@pytest.mark.parametrize("rows, place, message", [
    ('[\n  {"number": "CT 100", "day": "2026-12-11", "departs": "07:05"}\n]', "data/flights.json:2",
     'record 1 has no field "fare"'),
    ('[{"number": "CT 100", "day": "2026-12-11", "departs": "07:05", "fare": 219, "price": 1}]', "data/flights.json:1",
     'record 1 has a field "price" that Flight does not have'),
    (ROWS.replace("189", '"189"'), "data/flights.json:3", 'record 2 field "fare" is "189", not a whole number'),
    (ROWS.replace("189", "true"), "data/flights.json:3", 'record 2 field "fare" is true, not a whole number'),
    (ROWS.replace("189", "189.5"), "data/flights.json:3", 'record 2 field "fare" is 189.5, not a whole number'),
    (ROWS.replace('"2026-12-12"', '"12/12/2026"'), "data/flights.json:3",
     'record 2 field "day" is "12/12/2026", not a date like "2026-12-11"'),
    (ROWS.replace('"2026-12-12"', '"2026-13-40"'), "data/flights.json:3",
     'record 2 field "day" is "2026-13-40", not a date like "2026-12-11"'),
    (ROWS.replace('"07:05", "fare": 189', '"7:05 AM", "fare": 189'), "data/flights.json:3",
     'record 2 field "departs" is "7:05 AM", not a time like "07:05"'),
    (ROWS.replace('"CT 100", "day": "2026-12-12"', '100, "day": "2026-12-12"'), "data/flights.json:3",
     'record 2 field "number" is 100, not a string'),
    (ROWS.replace("2026-12-12", "2026-12-11"), "data/flights.json:3",
     'record 2 has the key of record 1: number "CT 100", day "2026-12-11"'),
    ('[\n  {"number": "CT 100", "day": "2026-12-11", "departs": "07:05", "fare": 219},\n\n  "CT 104"\n]',
     "data/flights.json:4", 'record 2 is "CT 104", not an object'),
    ('\n{"number": "CT 100"}', "data/flights.json:2", "a table's file holds an array of records, and this one does not"),
])
def test_a_record_that_is_not_what_its_class_says_is_vt206_naming_the_file_the_record_and_the_field(
        tmp_path, monkeypatch, rows, place, message):
    error = rejected(tmp_path, monkeypatch, rows=rows)
    assert (error.code, error.place, error.message) == ("VT206", place, message)
    assert error.fix


def test_a_file_that_is_not_json_is_vt206_at_the_line_that_breaks(tmp_path, monkeypatch):
    error = rejected(tmp_path, monkeypatch, rows='[\n  {"number": "CT 100"},\n  {"number": }\n]')
    assert (error.code, error.place) == ("VT206", "data/flights.json:3")
    assert error.message.startswith("not valid JSON: ")


def test_a_single_record_with_a_wrong_value_is_vt206(tmp_path, monkeypatch):
    source = ('import videotape as vt\n\n\nclass Traveler(vt.Record):\n    name: str\n    miles: int\n\n\n'
              'traveler = vt.one(Traveler, "data/flights.json")\n')
    error = rejected(tmp_path, monkeypatch, source, '{"name": "Alex Rivera", "miles": "many"}\n')
    assert (error.code, error.place) == ("VT206", "data/flights.json:1")
    assert error.message == 'the record field "miles" is "many", not a whole number'


@pytest.mark.parametrize("query", [
    lambda: DRINKS.where(cost=3),
    lambda: DRINKS.order_by("cost"),
    lambda: DRINKS.get(cost=3),
    lambda: DRINKS.distinct("cost"),
    lambda: DRINKS.min("cost"),
    lambda: DRINKS.group_by(lambda drink: drink.size).sum("cost"),
])
def test_a_query_that_names_a_field_its_records_lack_is_vt207_listing_their_fields(query):
    with pytest.raises(vt.ScreenplayError) as raised:
        query()
    error = raised.value
    assert (error.code, error.message) == ("VT207", 'Drink has no field "cost"')
    assert error.place.startswith(f"{HERE}:")
    assert error.fix == "name one of its fields: name, price, size"


def test_a_key_that_names_a_field_its_record_lacks_is_vt207():
    with pytest.raises(vt.ScreenplayError) as raised:
        class Cup(vt.Record, key="nme"):
            name: str
    assert (raised.value.code, raised.value.message) == ("VT207", 'Cup has no field "nme"')
    assert raised.value.fix == "name one of its fields: name"


def test_first_of_no_rows_is_vt208_at_the_line_that_asked():
    with pytest.raises(vt.ScreenplayError) as raised:
        DRINKS.where(size="huge").first()
    assert (raised.value.code, raised.value.message) == ("VT208", "first() found no Drink from drinks.json to return")
    assert raised.value.place.startswith(f"{HERE}:")


def test_get_needs_exactly_one_match_or_is_vt208():
    with pytest.raises(vt.ScreenplayError) as none:
        DRINKS.get(name="Chai")
    assert (none.value.code, none.value.message) == ("VT208", "get(name='Chai') matched no Drink from drinks.json")
    with pytest.raises(vt.ScreenplayError) as several:
        DRINKS.get(size="tall")
    assert several.value.code == "VT208"
    assert several.value.message == ("get(size='tall') matched 2 rows of Drink from drinks.json, and get() returns "
                                     "the only match")
    assert several.value.fix == "name the fields of its key, name, or use where(...) for several rows"
