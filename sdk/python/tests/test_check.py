import pytest
from conftest import BROKEN, SAMPLES, load_broken, load_sample

import videotape as vt
from videotape.check import RULES, check
from videotape.graph import Edge, Graph, closed_cycles, components, has_exit, journey, reachable
from videotape.serialize import build


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

    async def a(ctx, n: first):  # type: ignore[valid-type]
        return vt.stay()

    async def b(ctx, n: second):  # type: ignore[valid-type]
        return vt.stay()

    tape = vt.tape("t", [vt.frame("One", id="one", edit=first, submit=a, actions=[vt.action("Two", vt.goto("two"))]),
                         vt.frame("Two", id="two", edit=second, submit=b, actions=[vt.action("Back", vt.back())])])  # fmt: skip
    assert codes(vt.app("x", entry="t", tapes=[tape])) == ["duplicate-id"]


def test_unknown_hub_destination_and_hub_arguments():
    async def load(ctx, id: str) -> vt.Record: ...

    home = vt.tape("home", [vt.frame("Start", actions=[vt.action("Back", vt.back())])])
    item = vt.tape("item", [vt.frame("See one", enter=load, actions=[vt.action("Back", vt.back())])])
    hub = vt.hub([vt.destination("home", "Home"), vt.destination("item", "Item"), vt.destination("gone", "Gone")])
    diagnostics = check(vt.app("x", entry="home", tapes=[home, item], hub=hub))
    assert [(d.code, d.at) for d in diagnostics] == [
        ("unknown-tape", "hub"), ("loader-returns", "item"), ("missing-argument", "hub")]  # fmt: skip


def test_a_move_target_is_a_valid_parameter():
    from enum import Enum

    class Stage(Enum):
        A = "a"

    class Card(vt.Record):
        stage: Stage

    class Board(vt.Record):
        cards: list[Card] = vt.Field(group_by=Card.stage)

    async def move(ctx, card: Card, to: Stage):
        return vt.stay()

    async def wrong(ctx, card: Card, to: Stage):
        return vt.stay()

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

    async def find(ctx, s: Search):
        return vt.stay()

    f = vt.frame("Find", shows=Results, edit=Search, on_change={Results.q: find},
                 actions=[vt.action("Back", vt.back())])  # fmt: skip
    assert codes(vt.app("x", entry="s", tapes=[vt.tape("s", [f])])) == ["unknown-field"]


def test_unreadable_annotations_are_reported_once_per_handler():
    from future_handlers import nameless

    class Order(vt.Record):
        text: str

    a = vt.frame("One", id="one", edit=Order, submit=nameless, actions=[vt.action("Two", vt.goto("two"))])
    b = vt.frame("Two", id="two", edit=Order, submit=nameless, actions=[vt.action("Back", vt.back())])
    diagnostics = check(vt.app("x", entry="t", tapes=[vt.tape("t", [a, b])]))
    assert [(d.code, d.at) for d in diagnostics] == [("unreadable-outcome", "nameless()")]
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


# ── arguments, from bodies and static outcomes (Q34) ─────────────────────────


class _Order(vt.Record):
    id: vt.Id
    total: vt.Money


async def _load_order(ctx, order_id: str) -> _Order: ...


def _orders_app(handler):
    home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Open", handler), vt.action("Back", vt.back())])])
    order = vt.tape("order", [vt.frame("See one order", address="/o/{order_id}", shows=_Order, enter=_load_order,
                                       actions=[vt.action("Back", vt.back())])])  # fmt: skip
    return vt.app("orders", entry="home", tapes=[home, order])


def test_arguments_read_from_a_body_meet_the_target_loader():
    async def good(ctx):
        return vt.jump("order", order_id="o1")

    async def unknown(ctx):
        return vt.jump("order", order_id="o1", colour="red")

    async def missing(ctx):
        return vt.jump("order")

    async def splat(ctx):
        args = {"order_id": "o1"}
        return vt.jump("order", **args)

    assert codes(_orders_app(good)) == []
    assert codes(_orders_app(splat)) == []
    [d] = check(_orders_app(unknown))
    assert (d.code, d.message) == ("unknown-argument", "unknown() does jump('order', colour=...), but _load_order() does not take it")
    [d] = check(_orders_app(missing))
    assert (d.code, d.message) == ("missing-argument", "missing() does jump('order') without order_id, which _load_order() needs")


# ── history and the hub (Q31, Q32) ───────────────────────────────────────────


def _hub_app():
    async def sign_in(ctx):
        return vt.jump("home", sign_in=True)

    landing = vt.tape("landing", [vt.frame("Say what this is", actions=[vt.action("Sign in", sign_in)])])
    home = vt.tape("home", [vt.frame("See home", actions=[vt.action("Open", vt.jump("item")),
                                                          vt.action("Pick", vt.call("pick"))])])  # fmt: skip
    item = vt.tape("item", [vt.frame("See one item")])
    story = vt.tape("story", [vt.frame("Watch a story", hub=False)])
    pick = vt.tape("pick", [vt.frame("Pick something", actions=[vt.action("This", vt.done(1))])])
    settings = vt.tape("settings", [vt.frame("Change settings", actions=[vt.action("Story", vt.jump("story"))])])
    hub = vt.hub([vt.destination("home", "Home"), vt.destination("settings", "Settings")])
    return vt.app("x", entry="landing", tapes=[landing, home, item, story, pick, settings], hub=hub)


def test_roots_have_no_back_and_everything_else_does():
    app = _hub_app()
    j = journey(app, build(app).edges)
    assert j.roots == {"landing", "home", "settings"}  # the entry, the destinations, a sign-in's target
    assert [e.source for e in j.backs] == ["item", "story", "pick"]


def test_the_hub_shows_where_history_began_at_a_destination():
    app = _hub_app()
    j = journey(app, build(app).edges)
    assert sorted({e.source for e in j.doors}) == ["home", "item", "settings"]
    # not on landing (its root is not a destination), a story (hub=False), or a call's sheet
    assert j.began["item"] == {"home"}


def test_back_counts_as_a_way_out_but_roots_need_one_of_their_own():
    app = _hub_app()
    assert codes(app) == []
    end = vt.tape("end", [vt.frame("Thank you", back=False)])
    start = vt.tape("start", [vt.frame("Start", actions=[vt.action("Finish", vt.jump("end"))])])
    assert [(d.code, d.at) for d in check(vt.app("x", entry="start", tapes=[start, end]))] == [("no-exit", "end")]
    lonely = vt.tape("start", [vt.frame("Start")])
    [d] = check(vt.app("x", entry="start", tapes=[lonely]))
    assert d.code == "no-exit" and "history root" in d.message


def test_a_sign_out_target_is_a_root_with_no_back():
    async def leave(ctx):
        return vt.jump("bye", sign_out=True)

    start = vt.tape("start", [vt.frame("Start", actions=[vt.action("Sign out", leave)])])
    bye = vt.tape("bye", [vt.frame("Say goodbye")])
    [d] = check(vt.app("x", entry="start", tapes=[start, bye]))
    assert (d.code, d.at) == ("no-exit", "bye")


def errors_of(app):
    return [d for d in check(app) if d.level == "error"]


def errors(app):
    return [d.code for d in errors_of(app)]


# ── which document is meant (Q38) ────────────────────────────────────────────


class _Entry(vt.Record):
    slug: vt.Id
    title: str


class _Page(vt.Record):
    title: str
    toc: list[_Entry] = vt.Field(select=vt.jump("docs", page=_Entry.slug))   # its own item: fine


class _Search(vt.Record):
    q: str = vt.Field(kind="search", commit="change")
    results: list[_Entry] = vt.Field(select=vt.jump("docs", page=_Entry.slug))


async def _find(ctx, s: _Search):
    return vt.stay()


async def _load_page(ctx, page: str = "intro") -> _Page: ...


def _docs(**frame):
    f = vt.frame("Read the docs", shows=_Page, edit=_Search, enter=_load_page, on_change={_Search.q: _find}, **frame)
    return vt.app("docs", entry="docs", tapes=[vt.tape("docs", [f])])


def test_a_record_held_twice_is_named_by_its_field():
    assert errors(_docs()) == []

    async def open_entry(ctx, e: _Entry):
        return vt.stay()

    assert errors(_docs(actions=[vt.action("Open", open_entry, on=_Page.toc)])) == []
    assert errors(_docs(actions=[vt.action("Open", open_entry, on=_Entry)])) == ["ambiguous-record"]  # the on=, once
    assert errors(_docs(components=[vt.show(_Entry.title, role="heading")])) == ["ambiguous-record"]


def test_a_handler_parameter_held_twice_is_ambiguous_unless_the_action_names_it():
    async def bookmark(ctx, e: _Entry):
        return vt.stay()

    [d] = errors_of(_docs(actions=[vt.action("Bookmark", bookmark)]))
    assert d.code == "ambiguous-record" and "holds _Entry 2 times" in d.message


# ── forms and paging (Q35, deviation 1) ──────────────────────────────────────


def test_an_edit_frame_may_hide_only_the_id():
    class Line(vt.Record):
        product: str
        secret_sku: str = vt.Field(show=False)

    class Order(vt.Record):
        id: vt.Id
        note: str = vt.Field("", show=False)            # hidden, but it has a default
        lines: list[Line] = vt.Field(min_items=1)

    async def place(ctx, o: Order):
        return vt.stay()

    app = vt.app("x", entry="o", tapes=[vt.tape("o", [vt.frame("Place an order", edit=Order, submit=place)])])
    [d] = errors_of(app)
    assert d.code == "hidden-required" and "edits Line, whose required secret_sku" in d.message


def test_pages_loaders_return_the_list_s_items_and_take_its_holder():
    class Wall(vt.Record):
        id: vt.Id
        posts: list[_Entry]
        title: str

    @vt.pages(Wall.posts)
    async def wall_page(ctx, w: Wall, cursor: str | None) -> vt.Page[_Entry]: ...

    @vt.pages(Wall.title)
    async def title_page(ctx, cursor: str | None) -> vt.Page[str]: ...

    class Other(vt.Record):
        id: vt.Id
        posts: list[_Entry]

    @vt.pages(Other.posts)
    async def other_page(ctx, w: Wall, page: int) -> vt.Page[_Page]: ...

    def app(record):
        return vt.app("x", entry="w", tapes=[vt.tape("w", [vt.frame("See the wall", shows=record)])])

    assert [(d.code, d.at) for d in errors_of(app(Wall))] == [("loader-returns", "title_page()")]
    assert [d.code for d in errors_of(app(Other))] == ["loader-returns", "unknown-document", "unknown-document"]
