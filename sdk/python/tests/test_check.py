import pytest
from conftest import BROKEN, SAMPLES, load_broken, load_sample

import videotape as vt
from videotape.check import RULES, check
from videotape.graph import Graph, closed_cycles, components, has_exit, reachable
from videotape.serialize import Edge


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_every_sample_checks_clean(name):
    assert check(load_sample(name).app) == []


@pytest.mark.parametrize("code", sorted(RULES))
def test_each_rule_has_a_broken_fixture_that_trips_only_it(code):
    module = code.replace("-", "_")
    assert (BROKEN / f"{module}.py").exists(), f"no broken fixture for {code}"
    diagnostics = check(load_broken(module).app)
    assert {d.code for d in diagnostics} == {code}, [str(d) for d in diagnostics]
    level, _ = RULES[code]
    assert {d.level for d in diagnostics} == {level}


def test_every_broken_fixture_is_a_rule():
    assert {p.stem.replace("_", "-") for p in BROKEN.glob("*.py")} == set(RULES)


def test_app_check_is_check():
    app = load_broken("no_exit").app
    assert app.check() == check(app)


# ── rules beyond their fixtures ──────────────────────────────────────────────


def codes(app):
    return [d.code for d in check(app)]


def test_duplicate_tapes_and_frames():
    a = vt.tape("a", [vt.frame("One", id="one", actions=[vt.action("Back", vt.back())]),
                      vt.frame("Two", id="one", actions=[vt.action("Back", vt.back())])])  # fmt: skip
    again = vt.tape("a", [vt.frame("Three", actions=[vt.action("Back", vt.back())])])
    diagnostics = check(vt.app("x", entry="a", tapes=[a, again]))
    assert [d.message for d in diagnostics if d.code == "duplicate-id"] == [
        "tape 'a' is defined more than once", "frame 'one' is defined more than once"]  # fmt: skip


def test_duplicate_records():
    def make():
        class Note(vt.Record):
            text: str

        return Note

    first, second = make(), make()

    async def a(ctx, n: first) -> vt.Stay: ...  # type: ignore[valid-type]
    async def b(ctx, n: second) -> vt.Stay: ...  # type: ignore[valid-type]

    tape = vt.tape("t", [vt.frame("One", edit=first, submit=a, actions=[vt.action("Two", vt.goto("two"))]),
                         vt.frame("Two", id="two", edit=second, submit=b, actions=[vt.action("Back", vt.back())])])  # fmt: skip
    assert codes(vt.app("x", entry="t", tapes=[tape])) == ["duplicate-id"]


def test_unknown_hub_destination_and_hub_arguments():
    async def load(ctx, id: str) -> vt.Record: ...

    home = vt.tape("home", [vt.frame("Start", actions=[vt.action("Back", vt.back())])])
    item = vt.tape("item", [vt.frame("See one", enter=load, actions=[vt.action("Back", vt.back())])])
    hub = vt.hub([vt.destination("home", "Home"), vt.destination("item", "Item"), vt.destination("gone", "Gone")])
    diagnostics = check(vt.app("x", entry="home", tapes=[home, item], hub=hub))
    assert [(d.code, d.at) for d in diagnostics] == [
        ("unknown-tape", "hub"), ("loader-returns", "item/see-one"), ("missing-argument", "hub")]  # fmt: skip


def test_a_move_target_is_a_valid_parameter():
    from enum import Enum

    class Stage(Enum):
        A = "a"

    class Card(vt.Record):
        stage: Stage

    class Board(vt.Record):
        cards: list[Card] = vt.Field(group_by=Card.stage)

    async def move(ctx, card: Card, to: Stage) -> vt.Stay: ...
    async def wrong(ctx, card: Card, to: Stage) -> vt.Stay: ...

    ok = vt.frame("See the board", shows=Board, actions=[
        vt.action("Move", move, on=Card, to=Stage), vt.action("Back", vt.back())])  # fmt: skip
    assert codes(vt.app("x", entry="b", tapes=[vt.tape("b", [ok])])) == []
    bad = vt.frame("See the board", shows=Board, actions=[vt.action("Move", wrong, on=Card), vt.action("Back", vt.back())])
    assert codes(vt.app("x", entry="b", tapes=[vt.tape("b", [bad])])) == ["unknown-document"]


def test_on_change_must_name_an_edited_field():
    class Search(vt.Record):
        q: str

    class Results(vt.Record):
        q: str

    async def find(ctx, s: Search) -> vt.Stay: ...

    f = vt.frame("Find", shows=Results, edit=Search, on_change={Results.q: find},
                 actions=[vt.action("Back", vt.back())])  # fmt: skip
    assert codes(vt.app("x", entry="s", tapes=[vt.tape("s", [f])])) == ["unknown-field"]


def test_unreadable_annotations_are_reported_once_per_handler():
    from future_handlers import nameless

    class Order(vt.Record):
        text: str

    a = vt.frame("One", edit=Order, submit=nameless, actions=[vt.action("Two", vt.goto("two"))])
    b = vt.frame("Two", id="two", edit=Order, submit=nameless, actions=[vt.action("Back", vt.back())])
    diagnostics = check(vt.app("x", entry="t", tapes=[vt.tape("t", [a, b])]))
    assert [(d.code, d.at) for d in diagnostics] == [("unreadable-return", "nameless()")]
    assert "Missing" in diagnostics[0].message


# ── the graph, as in prototype-0 ─────────────────────────────────────────────


def g(entry, nodes, edges):
    return Graph(entry, nodes, [Edge(a, t, {}, None, b) for a, t, b in edges])


def test_reachable_follows_edges_and_back_adds_nothing():
    graph = g("a", ["a", "b", "c", "d"], [("a", "jump", "b"), ("b", "back", None), ("c", "jump", "d")])
    assert reachable(graph) == {"a", "b"}


def test_exits():
    graph = g("a", ["a", "b", "c"], [("a", "jump", "a"), ("b", "back", None), ("c", "done", None)])
    assert [has_exit(graph, n) for n in graph.nodes] == [False, True, True]


def test_components_and_closed_cycles():
    graph = g("a", ["a", "b", "c", "d"], [("a", "jump", "b"), ("b", "jump", "c"), ("c", "jump", "b"), ("d", "jump", "a")])
    assert sorted(sorted(c) for c in components(graph)) == [["a"], ["b", "c"], ["d"]]
    assert closed_cycles(graph) == [["b", "c"]]
    graph.edges.append(Edge("c", "back", {}))
    assert closed_cycles(graph) == []


def test_the_entry_s_own_cycle_is_no_trap():
    graph = g("a", ["a", "b"], [("a", "jump", "b"), ("b", "jump", "a")])
    assert closed_cycles(graph) == []
