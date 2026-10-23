"""Tracking: what a handler changes in its documents becomes ops (05 §6.2)."""

import asyncio
import copy

import pytest

import videotape as vt
from videotape.records import _tracked
from videotape.tracking import KEY, Tracker, dump, key_of, keys_scope, load


class Author(vt.Record):
    id: vt.Id
    name: str


class Line(vt.Record):
    text: str
    done: bool = False


class Note(vt.Record):
    id: vt.Id
    title: str
    author: Author | None = None
    lines: list[Line] = []
    tags: list[str] = []
    people: list[Author] = []


class Login(vt.Record):
    username: str
    password: vt.Secret


REF = {"record": "Note", "id": "n1"}


def note_json():
    return {
        "id": "n1", "title": "Plan", "author": {"id": "a1", "name": "Ada"},
        "lines": [{"text": "one", KEY: "~e1"}, {"text": "two", KEY: "~e2"}],
        "tags": ["x"], "people": [{"id": "a2", "name": "Bo"}],
    }  # fmt: skip


def run(body):
    """Runs `body(tracker)` in an event loop and returns the ops it produced, flushed by turn."""
    batches = []

    async def main():
        with keys_scope():
            t = Tracker(lambda changes, decision: batches.append((decision, changes)), "d1")
            await body(t)
            t.close()

    asyncio.run(main())
    return batches


def ops(batches):
    return [op for _, changes in batches for change in changes for op in change["ops"]]


def test_assignment_is_a_set_op_on_its_path():
    async def body(t):
        note = t.adopt(Note, note_json(), REF)
        note.title = "Plan B"
        note.author.name = "Ada L."
        note.lines[1].done = True

    assert ops(run(body)) == [
        {"op": "set", "path": ["title"], "value": "Plan B"},
        {"op": "set", "path": ["author", "name"], "value": "Ada L."},
        {"op": "set", "path": ["lines", {"key": "~e2"}, "done"], "value": True},
    ]


def test_changes_in_one_turn_are_one_sync_and_carry_the_decision():
    async def body(t):
        note = t.adopt(Note, note_json(), REF)
        note.title = "a"
        note.title = "b"
        await asyncio.sleep(0)
        note.title = "c"

    batches = run(body)
    assert [d for d, _ in batches] == ["d1", "d1"]
    assert [len(changes[0]["ops"]) for _, changes in batches] == [2, 1]
    assert batches[0][1][0]["doc"] == REF


def test_list_changes_address_items_by_key():
    async def body(t):
        note = t.adopt(Note, note_json(), REF)
        added = note.lines.append(Line(text="three"))
        assert isinstance(added, Line)
        added.done = True                                  # the returned item is tracked
        note.lines.prepend({"text": "zero"})
        note.lines.insert(2, Line(text="one and a half"))
        note.lines.remove(note.lines[1])
        note.lines.pop()

    found = ops(run(body))
    inserted = [o for o in found if o["op"] == "insert"]
    assert [o["at"] for o in inserted] == ["end", "start", {"before": "~e2"}]
    assert [o["value"]["text"] for o in inserted] == ["three", "zero", "one and a half"]
    assert all(o["path"] == ["lines"] and o["key"].startswith("~") for o in inserted)
    assert found[1] == {"op": "set", "path": ["lines", {"key": inserted[0]["key"]}, "done"], "value": True}
    removed = [o for o in found if o["op"] == "remove"]
    assert [o["key"] for o in removed] == ["~e1", inserted[0]["key"]]


def test_items_with_an_id_are_keyed_by_it_and_replaced_by_it():
    async def body(t):
        note = t.adopt(Note, note_json(), REF)
        note.people.append(Author(id="a3", name="Cy"))
        note.people.replace(Author(id="a2", name="Bo B."))
        with pytest.raises(ValueError):
            note.people.replace(Author(id="zz", name="?"))
        with pytest.raises(TypeError):
            note.lines.replace(Line(text="no id"))

    found = ops(run(body))
    assert found[0]["key"] == "a3"
    assert found[1] == {"op": "replace", "path": ["people"], "key": "a2", "value": {"id": "a2", "name": "Bo B."}}


def test_lists_of_plain_values_and_reorders_change_as_a_whole():
    async def body(t):
        note = t.adopt(Note, note_json(), REF)
        note.tags.append("y")
        note.lines.reverse()
        note.tags = ["z"]

    found = ops(run(body))
    assert found[0] == {"op": "set", "path": ["tags"], "value": ["x", "y"]}
    assert found[1]["op"] == "set" and [v[KEY] for v in found[1]["value"]] == ["~e2", "~e1"]
    assert found[2] == {"op": "set", "path": ["tags"], "value": ["z"]}


def test_a_list_assigned_whole_is_tracked_again():
    async def body(t):
        note = t.adopt(Note, note_json(), REF)
        note.lines = [Line(text="fresh")]
        note.lines[0].done = True

    found = ops(run(body))
    key = found[0]["value"][0][KEY]
    assert found[1] == {"op": "set", "path": ["lines", {"key": key}, "done"], "value": True}


def test_secrets_are_never_sent():
    async def body(t):
        login = t.adopt(Login, {"username": "ada", "password": "hunter2"}, {"record": "Login", "local": "d1"})
        assert login.password == "hunter2"
        login.password = "other"
        login.username = "bo"

    found = ops(run(body))
    assert found == [{"op": "set", "path": ["username"], "value": "bo"}]
    assert "hunter2" not in repr(found) and "other" not in repr(found)
    assert "password" not in dump(Login(username="a", password="b"))


def test_validation_happens_before_the_op():
    async def body(t):
        note = t.adopt(Note, note_json(), REF)
        with pytest.raises(Exception):
            note.title = 5
        with pytest.raises(Exception):
            note.lines.append({"nope": 1})

    assert ops(run(body)) == []


def test_closing_stops_tracking_and_forgets_everything():
    kept = {}

    async def body(t):
        kept["note"] = t.adopt(Note, note_json(), REF)

    run(body)
    before = len(_tracked)
    kept["note"].title = "after"                           # nothing to send it to
    assert len(_tracked) == before == 0


def test_copies_are_plain():
    async def body(t):
        note = t.adopt(Note, note_json(), REF)
        clone = copy.deepcopy(note)
        assert type(clone.lines) is list
        clone.title = "copy"

    assert ops(run(body)) == []


def test_load_and_dump_round_trip_keys():
    with keys_scope():
        note = load(Note, note_json())
        assert [key_of(line) for line in note.lines] == ["~e1", "~e2"]
        expected = note_json()
        for line in expected["lines"]:
            line["done"] = False
        expected["people"][0][KEY] = "a2"                  # an item with an Id is keyed by it
        assert dump(note) == expected
