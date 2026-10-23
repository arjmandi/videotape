import pytest
from conftest import BROKEN, SAMPLES, load_broken, load_clean, load_sample

import videotape as vt
from videotape.check import RULES, check
from videotape.records import fields_of
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


MORE = vt.tape("more", [vt.frame("Read more")])
"""Somewhere to go: a root frame's explicit back is no way out (Q44)."""
OUT = vt.action("More", vt.jump("more"))


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

    home = vt.tape("home", [vt.frame("Start", actions=[OUT])])
    item = vt.tape("item", [vt.frame("See one", enter=load, actions=[OUT])])
    hub = vt.hub([vt.destination("home", "Home"), vt.destination("item", "Item"), vt.destination("gone", "Gone")])
    diagnostics = check(vt.app("x", entry="home", tapes=[home, item, MORE], hub=hub))
    assert [(d.code, d.at) for d in diagnostics] == [
        ("unknown-tape", "hub"), ("loader-returns", "item"), ("missing-argument", "hub")]  # fmt: skip


def test_a_move_target_is_a_valid_parameter():
    from enum import Enum

    class Stage(Enum):
        A = "a"

    class Card(vt.Record):
        stage: Stage

    class Board(vt.Record):
        cards: list[Card] = vt.Field([], group_by=Card.stage)

    async def move(ctx, card: Card, to: Stage):
        return vt.stay()

    async def wrong(ctx, card: Card, to: Stage):
        return vt.stay()

    ok = vt.frame("See the board", shows=Board, actions=[
        vt.action("Move", move, on=Card, to=Stage), OUT])  # fmt: skip
    assert codes(vt.app("x", entry="b", tapes=[vt.tape("b", [ok]), MORE])) == []
    bad = vt.frame("See the board", shows=Board, actions=[vt.action("Move", wrong, on=Card), OUT])
    assert codes(vt.app("x", entry="b", tapes=[vt.tape("b", [bad]), MORE])) == ["unknown-document"]


def test_on_change_must_name_an_edited_field():
    class Search(vt.Record):
        q: str

    class Results(vt.Record):
        q: str = ""

    async def find(ctx, s: Search):
        return vt.stay()

    f = vt.frame("Find", shows=Results, edit=Search, on_change={Results.q: find},
                 actions=[OUT])  # fmt: skip
    assert codes(vt.app("x", entry="s", tapes=[vt.tape("s", [f]), MORE])) == ["unknown-field"]


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
    home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Open", handler), OUT])])
    order = vt.tape("order", [vt.frame("See one order", address="/o/{order_id}", shows=_Order, enter=_load_order,
                                       actions=[OUT])])  # its address opens it as a root (Q48)
    return vt.app("orders", entry="home", tapes=[home, order, MORE])


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
    assert (d.code, d.message) == ("unknown-argument",
                                   "unknown() does jump('order', colour=...), but no loader or address in tape 'order' takes it")
    [d] = check(_orders_app(missing))
    assert (d.code, d.message) == ("missing-argument", "missing() does jump('order') without order_id: _load_order() needs order_id")


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


class _Results(vt.Record):
    hits: list[_Entry] = vt.Field([], select=vt.jump("docs", page=_Entry.slug))


async def _find(ctx, s: _Search, r: _Results):
    return vt.stay()


async def _load_page(ctx, page: str = "intro") -> _Page: ...


def _docs(**frame):
    f = vt.frame("Read the docs", shows=[_Page, _Results], edit=_Search, enter=_load_page,
                 on_change={_Search.q: _find}, **frame)  # fmt: skip
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
        posts: list[_Entry] = []
        title: str = ""

    @vt.pages(Wall.posts)
    async def wall_page(ctx, w: Wall, cursor: str | None) -> vt.Page[_Entry]: ...

    @vt.pages(Wall.title)
    async def title_page(ctx, cursor: str | None) -> vt.Page[str]: ...

    class Other(vt.Record):
        id: vt.Id
        posts: list[_Entry] = []

    @vt.pages(Other.posts)
    async def other_page(ctx, w: Wall, page: int) -> vt.Page[_Page]: ...

    def app(record):
        return vt.app("x", entry="w", tapes=[vt.tape("w", [vt.frame("See the wall", shows=record)])])

    assert [(d.code, d.at) for d in errors_of(app(Wall))] == [("loader-returns", "title_page()")]
    assert [d.code for d in errors_of(app(Other))] == ["loader-returns", "unknown-document", "unknown-document"]


def test_show_on_a_list_names_which_items(  # Q41
):
    assert errors(_docs(components=[vt.show(_Entry.title, on=_Page.toc, role="heading")])) == []
    [d] = errors_of(_docs(components=[vt.show(_Entry.title, on=_Page.title)]))
    assert d.code == "unknown-field" and "on= names a list of records" in d.message
    [d] = errors_of(_docs(components=[vt.show(_Page.title, on=_Page.toc)]))
    assert d.code == "unknown-field" and "not a field of _Page.toc's items" in d.message


def test_a_chained_reference_resolves_from_its_root():
    class Address(vt.Record):
        city: str

    class Customer(vt.Record):
        billing: Address
        shipping: Address

    async def load(ctx) -> Customer: ...

    def app(ref):
        f = vt.frame("See a customer", shows=Customer, enter=load, components=[vt.show(ref, role="heading")])
        return vt.app("x", entry="c", tapes=[vt.tape("c", [f])])

    assert errors(app(Customer.billing.city)) == []  # Address is held twice; the chain says which
    assert errors(app(Address.city)) == ["ambiguous-record"]


def test_a_loader_returns_one_document_or_a_tuple():  # Q42
    async def both(ctx, page: str = "intro") -> tuple[_Page, _Results]: ...

    async def wrong(ctx, page: str = "intro") -> tuple[_Page, _Entry]: ...

    def app(loader):
        f = vt.frame("Read", shows=[_Page, _Results], edit=_Search, enter=loader, on_change={_Search.q: _find})
        return vt.app("docs", entry="docs", tapes=[vt.tape("docs", [f])])

    assert errors(app(both)) == []
    [d] = errors_of(app(wrong))
    assert d.code == "loader-returns" and "returns _Entry" in d.message


# ── arguments belong to the tape (Q46) ───────────────────────────────────────


class _Draft(vt.Record):
    title: str = ""


class _Summary(vt.Record):
    title: str = ""


async def _load_start(ctx, order_id: str) -> _Draft: ...


async def _load_confirm(ctx, draft: _Draft, coupon: str | None = None) -> _Summary: ...


async def _load_lost(ctx, summary: _Summary) -> _Summary: ...


async def _to_confirm(ctx, d: _Draft):
    return vt.goto("confirm")


def _wizard(jump, confirm_loader=_load_confirm):
    home = vt.tape("home", [vt.frame("Start", actions=[vt.action("Order", jump)])])
    wizard = vt.tape("wizard", [
        vt.frame("Write the order", id="start", edit=_Draft, enter=_load_start, submit=_to_confirm),
        vt.frame("Confirm the order", id="confirm", shows=_Summary, enter=confirm_loader),
    ])  # fmt: skip
    return vt.app("x", entry="home", tapes=[home, wizard])


def test_every_loader_in_a_tape_takes_its_arguments():
    assert errors(_wizard(vt.jump("wizard", order_id="o1"))) == []
    assert errors(_wizard(vt.jump("wizard", order_id="o1", coupon="SPRING"))) == []  # a later frame's loader
    [d] = errors_of(_wizard(vt.jump("wizard", order_id="o1", colour="red")))
    assert d.code == "unknown-argument" and "no loader or address in tape 'wizard' takes it" in d.message
    [d] = errors_of(_wizard(vt.jump("wizard")))
    assert d.code == "missing-argument" and "_load_start() needs order_id" in d.message


def test_a_later_loader_takes_earlier_frames_documents():
    assert errors(_wizard(vt.jump("wizard", order_id="o1"))) == []  # _load_confirm takes the draft
    [d] = errors_of(_wizard(vt.jump("wizard", order_id="o1"), confirm_loader=_load_lost))
    assert d.code == "unknown-document" and "no earlier frame of tape 'wizard'" in d.message


# ── explicit back on roots (Q44) ─────────────────────────────────────────────


def test_back_on_a_root_is_no_way_out():
    home = vt.tape("home", [vt.frame("Start", actions=[vt.action("Back", vt.back())])])
    diagnostics = check(vt.app("x", entry="home", tapes=[home]))
    assert [(d.code, d.level) for d in diagnostics] == [("back-on-root", "error"), ("no-exit", "warning")]


def test_back_on_a_sometimes_root_is_a_warning_and_the_intent_says_which():
    home = vt.tape("home", [vt.frame("Start", actions=[vt.action("Back", vt.back()), vt.action("More", vt.jump("more"))])])
    more = vt.tape("more", [vt.frame("Read more", actions=[vt.action("Home", vt.jump("home"))])])
    app = vt.app("x", entry="home", tapes=[home, more])
    assert [(d.code, d.level) for d in check(app)] == [("back-on-root-sometimes", "warning")]
    assert app.intent()["tapes"][0]["frames"][0]["root"] == "sometimes"


# ── shown records need a source (Q47) ────────────────────────────────────────


class _Profile(vt.Record):
    name: str
    bio: str = ""


def test_a_shown_record_needs_a_loader_an_earlier_frame_or_defaults():
    async def load(ctx) -> _Profile: ...

    async def unread(ctx): ...

    async def edit_it(ctx, p: _Profile):
        return vt.goto("view")

    def app(*frames):
        return vt.app("x", entry="p", tapes=[vt.tape("p", list(frames)), MORE])

    assert errors(app(vt.frame("See", shows=_Profile, enter=load, actions=[OUT]))) == []
    assert errors(app(vt.frame("See", shows=_Profile, enter=unread, actions=[OUT]))) == []  # cannot tell: no error
    assert errors(app(vt.frame("See", shows=_Draft, actions=[OUT]))) == []  # every field has a default
    assert errors(app(vt.frame("See", shows=list[_Profile], actions=[OUT]))) == []  # a list starts empty
    assert errors(app(vt.frame("Edit", id="edit", edit=_Profile, submit=edit_it, actions=[OUT]),
                      vt.frame("View", id="view", shows=_Profile, actions=[OUT]))) == []  # an earlier frame has it
    [d] = errors_of(app(vt.frame("See", shows=_Profile, actions=[OUT])))
    assert d.code == "unsourced-record" and "name has no default" in d.message


# ── addresses open frames directly (Q48, Q49) ────────────────────────────────


async def _load_thread(ctx, id: str) -> _Profile: ...


def _linked(hub: bool, **thread):
    chats = vt.tape("chats", [vt.frame("See chats", actions=[vt.action("Open", vt.jump("thread", id="c1"))])])
    settings = vt.tape("settings", [vt.frame("Change settings", actions=[vt.action("Open", vt.jump("thread", id="c1"))])])
    t = vt.tape("thread", [vt.frame("Read a thread", address="/c/{id}", shows=_Profile, enter=_load_thread, **thread)])
    destinations = vt.hub([vt.destination(settings, "Settings"), vt.destination(chats, "Chats")]) if hub else None
    return vt.app("x", entry=chats, tapes=[chats, settings, t], hub=destinations)


def test_with_a_hub_the_first_destination_that_reaches_a_linked_frame_goes_beneath_it():
    app = _linked(hub=True)
    j = journey(app, build(app).edges)
    assert j.beneath == {"thread": "settings"}  # hub order, not the entry
    assert "thread" not in j.roots and {e.source for e in j.backs} == {"thread"}
    assert {e.source for e in j.doors} >= {"thread"}
    assert errors(app) == [] and codes(app) == []


def test_without_a_hub_a_linked_frame_is_a_root_on_that_path():
    app = _linked(hub=False)
    j = journey(app, build(app).edges)
    assert "thread" in j.sometimes and "thread" not in {e.source for e in j.backs}
    [d] = [d for d in check(app) if d.at == "thread"]  # settings is unreachable without the hub
    assert d.code == "no-exit" and "a history root on some paths (its address opens it as one)" in d.message
    assert app.intent()["tapes"][2]["frames"][0]["root"] == "sometimes"
    linked = _linked(hub=False, actions=[vt.action("Back", vt.back())])
    assert [(d.code, d.level) for d in check(linked) if d.at == "thread"] == [("back-on-root-sometimes", "warning")]


def test_a_frame_only_a_link_opens_is_reachable_and_always_a_root():
    home = vt.tape("home", [vt.frame("Start", actions=[OUT])])
    linked = vt.tape("linked", [vt.frame("Read a thread", address="/c/{id}", shows=_Profile, enter=_load_thread,
                                         actions=[vt.action("Back", vt.back())])])  # fmt: skip
    diagnostics = check(vt.app("x", entry=home, tapes=[home, linked, MORE]))
    assert [(d.code, d.at) for d in diagnostics] == [("back-on-root", "linked"), ("no-exit", "linked")]


def test_a_linked_frame_stands_on_its_own():
    async def needs_more(ctx, id: str, coupon: str) -> _Profile: ...

    async def optional_more(ctx, id: str, coupon: str | None = None) -> _Profile: ...

    async def edit_it(ctx, p: _Profile):
        return vt.goto("view")

    async def from_earlier(ctx, p: _Profile, id: str) -> _Profile: ...

    def app(*frames, **args):
        home = vt.tape("home", [vt.frame("Start", actions=[vt.action("Open", vt.jump("t", **(args or {"id": "c1", "coupon": "X"})))])])
        return vt.app("x", entry=home, tapes=[home, vt.tape("t", list(frames)), MORE])

    def linked(loader, **kw):
        return vt.frame("Read", id="view", address="/c/{id}", shows=_Profile, enter=loader, actions=[OUT], **kw)

    assert errors(app(linked(optional_more))) == []  # a default supplies what the address does not
    [d] = errors_of(app(linked(needs_more)))
    assert d.code == "address-standalone" and "needs coupon, which it does not carry" in d.message
    first = vt.frame("Edit", id="edit", edit=_Profile, submit=edit_it, actions=[OUT])
    [d] = errors_of(app(first, linked(from_earlier), id="c1"))
    assert d.code == "address-standalone" and "takes p: _Profile" in d.message
    first = vt.frame("Edit", id="edit", edit=_Profile, submit=edit_it, actions=[OUT])
    view = vt.frame("Read", id="view", address="/read", shows=_Profile, actions=[OUT])
    [d] = errors_of(vt.app("x", entry="t", tapes=[vt.tape("t", [first, view]), MORE]))
    assert d.code == "address-standalone" and "which only an earlier frame of tape 't' has" in d.message


@pytest.mark.parametrize("name", ["fresh_start_sign_in", "fresh_start_hub"])
def test_a_closed_cycle_that_holds_a_fresh_start_is_not_reported(name):  # Q51, decided
    app = load_clean(name).app
    assert check(app) == []
    j = journey(app, build(app).edges)
    assert closed_cycles(j.graph) != []  # without the exception it would be one
    assert closed_cycles(j.graph, j.fresh) == []


def test_a_closed_cycle_after_a_sign_out_is_reported():  # Q51: sign-out targets are no fresh start
    async def leave(ctx):
        return vt.jump("bye", sign_out=True)

    start = vt.tape("start", [vt.frame("Start", actions=[vt.action("Sign out", leave)])])
    bye = vt.tape("bye", [vt.frame("Say goodbye", actions=[vt.action("Why", vt.jump("why"))])])
    why = vt.tape("why", [vt.frame("Say why", back=False, actions=[vt.action("Bye", vt.jump("bye"))])])
    assert [d.code for d in check(vt.app("x", entry=start, tapes=[start, bye, why]))] == ["closed-cycle"]


def test_what_follows_a_fresh_start_is_no_closed_cycle():
    async def sign_in(ctx):
        return vt.jump("dashboard", sign_in=True)

    landing = vt.tape("landing", [vt.frame("Welcome", actions=[vt.action("Sign in", sign_in)])])
    dashboard = vt.tape("dashboard", [vt.frame("See projects", actions=[vt.action("Report", vt.jump("report"))])])
    report = vt.tape("report", [vt.frame("Read a report", back=False, actions=[vt.action("All", vt.jump("dashboard"))])])
    assert codes(vt.app("x", entry=landing, tapes=[landing, dashboard, report])) == []


# ── a tape or its id, wherever a tape is named (Q50) ─────────────────────────


def test_a_tape_or_its_id_wherever_a_tape_is_named():
    home = vt.tape("home", [vt.frame("Start", actions=[vt.action("More", vt.jump(MORE))])])
    app = vt.app("x", entry=home, tapes=[home, MORE], hub=vt.hub([vt.destination(home, "Home"), vt.destination("more", "More")]))
    assert app.entry == "home" and [d.tape for d in app.hub.destinations] == ["home", "more"]
    assert app.intent()["hub"] == [{"tape": "home", "label": "Home"}, {"tape": "more", "label": "More"}]

    class Deal(vt.Record):
        company: _Profile = vt.pick(MORE)                     # works when the tape exists first
        owner: _Profile = vt.pick("more")                     # inside records, usually the id

    assert {f.options["pick"] for f in fields_of(Deal)} == {"more"}
    with pytest.raises(TypeError):
        vt.destination(3, "Three")
    with pytest.raises(TypeError):
        vt.app("x", entry=None, tapes=[home])


# ── the destination beneath a linked frame (Q52) ─────────────────────────────


def _two_ways(under=None, address="/c/{id}", hub=True):
    chats = vt.tape("chats", [vt.frame("See chats", actions=[vt.action("Open", vt.jump("thread", id="c1"))])])
    people = vt.tape("people", [vt.frame("See people", actions=[vt.action("Open", vt.jump("thread", id="c1"))])])
    settings = vt.tape("settings", [vt.frame("Change settings")])
    thread = vt.tape("thread", [vt.frame("Read a thread", address=address, shows=_Profile, enter=_load_thread,
                                         under=under, actions=[OUT])])  # fmt: skip
    destinations = [vt.destination(chats, "Chats"), vt.destination(people, "People"), vt.destination(settings, "Settings")]
    return vt.app("x", entry=chats, tapes=[chats, people, settings, thread, MORE],
                  hub=vt.hub(destinations) if hub else None)


def test_the_intent_carries_the_destination_beneath_a_linked_frame():
    def under(app):
        return next(t for t in app.intent()["tapes"] if t["id"] == "thread")["frames"][0].get("under")

    assert under(_two_ways()) == "chats"  # the first in hub order that reaches it
    app = _two_ways(under="people")
    assert under(app) == "people" and check(app) == []
    people = next(t for t in app.tapes if t.id == "people")
    assert under(_two_ways(under=people)) == "people"  # the tape itself works too
    assert under(_two_ways(hub=False)) is None


@pytest.mark.parametrize("make, words", [
    (lambda: _two_ways(under="settings"), "cannot reach this frame"),
    (lambda: _two_ways(under="landing"), "is not a hub destination"),
    (lambda: _two_ways(under="people", hub=False), "the app has no hub"),
    (lambda: _two_ways(under="people", address=None), "has none"),
])  # fmt: skip
def test_under_must_be_a_destination_that_reaches_a_linked_frame(make, words):
    [d] = errors_of(make())
    assert d.code == "bad-under" and words in d.message
