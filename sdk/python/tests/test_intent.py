import json
import os
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from conftest import SAMPLES, load_sample

import videotape as vt
from videotape.serialize import build
from videotape.spec import intent_schema

SCHEMA_FILE = Path(vt.__file__).parent / "intent.schema.json"


class Item(vt.Record):
    id: vt.Id
    sku: str = vt.Field(show=False)
    name: str = vt.Field(role="heading")
    price: vt.Money
    done: bool = vt.State(False)


class Basket(vt.Record):
    title: str
    items: list[Item] = vt.Field(select=vt.jump("item", item_id=Item.id))


class Note(vt.Record):
    text: vt.Text = vt.Field(lines=(2, 8))
    volume: int = vt.Field(ge=0, le=10)
    secret: vt.Secret


async def save(ctx, n: Note):
    return vt.stay()


def one_frame(**kwargs):
    f = vt.frame("Do one thing", **kwargs)
    a = vt.app("t", entry="a", tapes=[vt.tape("a", [f]), vt.tape("item", [vt.frame("See an item")])])
    return next(t for t in a.intent()["tapes"] if t["id"] == "a")["frames"][0]


# ── the samples ──────────────────────────────────────────────────────────────


def test_every_sample_serialises_to_valid_intent(sample):
    intent = sample.app.intent()
    jsonschema.Draft202012Validator(intent_schema()).validate(intent)
    assert intent["format"] == "videotape.intent/2"
    json.dumps(intent)  # plain JSON all the way down


def test_the_published_schema_is_current():
    assert json.loads(SCHEMA_FILE.read_text()) == intent_schema()
    jsonschema.Draft202012Validator.check_schema(intent_schema())


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_intent_is_deterministic_across_processes(name):
    directory, module = SAMPLES[name]
    script = f"import json, {module}; print(json.dumps({module}.app.intent(), ensure_ascii=False))"
    outputs = set()
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        run = subprocess.run([sys.executable, "-c", script], cwd=directory, env=env, capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        outputs.add(run.stdout)
    assert len(outputs) == 1
    assert outputs.pop().strip() == json.dumps(load_sample(name).app.intent(), ensure_ascii=False)


def test_record_schemas_validate_their_documents():
    m = load_sample("hello")
    intent = m.app.intent()
    root = {"records": intent["records"], "types": intent["types"]}

    def valid(record: str, doc: dict) -> bool:
        return jsonschema.Draft202012Validator({**root, "$ref": f"#/records/{record}"}).is_valid(doc)

    doc ={"title": "Q3", "chart": {"rows": [{"week": 1, "events": 2}], "x": "week", "y": "events"},
           "summary": {"blocks": [{"kind": "paragraph", "spans": [{"text": "Fine."}]}]}}  # fmt: skip
    assert valid("Report", doc)
    assert not valid("Report", {**doc, "chart": {"rows": []}})
    assert valid("Credentials", {"username": "ada", "password": "x"})
    assert not valid("Credentials", {"username": "ada"})


def test_every_property_carries_its_kind_under_x_vt(sample):
    for name, schema in sample.app.intent()["records"].items():
        if "properties" not in schema:
            continue  # an enum
        assert schema["x-vt"]["type"] == "record"
        for prop in schema["properties"].values():
            assert "type" in prop["x-vt"], name


# ── records in the intent ────────────────────────────────────────────────────


def test_records_and_built_in_types():
    f = vt.frame("Edit a note", edit=Note, submit=save)
    intent = vt.app("t", entry="a", tapes=[vt.tape("a", [f])]).intent()
    props = intent["records"]["Note"]["properties"]
    assert props["text"]["x-vt"] == {"type": "text", "lines": [2, 8]}
    assert props["secret"]["x-vt"] == {"type": "secret"}
    assert props["volume"]["minimum"] == 0 and props["volume"]["maximum"] == 10
    assert intent["types"] == {}

    f = vt.frame("See a basket", shows=Basket)
    intent = vt.app("t", entry="a", tapes=[vt.tape("a", [f]), vt.tape("item", [vt.frame("x")])]).intent()
    assert sorted(intent["records"]) == ["Basket", "Item"]
    price = intent["records"]["Item"]["properties"]["price"]
    assert price["x-vt"] == {"type": "money"}
    items = intent["records"]["Basket"]["properties"]["items"]
    assert items["items"] == {"$ref": "#/records/Item"}
    assert items["x-vt"]["select"] == {"type": "jump", "tape": "item", "args": {"item_id": {"field": "Item.id"}}}


def test_built_in_types_live_under_types():
    intent = load_sample("hello").app.intent()
    assert intent["records"]["Report"]["properties"]["summary"]["$ref"] == "#/types/vt.RichText"
    assert {"vt.RichText", "vt.Series", "vt.Span"} <= set(intent["types"])
    assert "description" not in intent["types"]["vt.RichText"]


# ── frames ───────────────────────────────────────────────────────────────────


def test_frame_ids_are_given_or_derived():
    t = vt.tape("a", [vt.frame("Sign in"), vt.frame("Sign in"), vt.frame("Confirm it", id="confirm")])
    assert [f.key for f in t.frames] == ["sign-in", "sign-in-2", "confirm"]
    frames = vt.app("x", entry="a", tapes=[t]).intent()["tapes"][0]["frames"]
    assert [(f["id"], f.get("derived_id")) for f in frames] == [("sign-in", True), ("sign-in-2", True), ("confirm", None)]


def test_edit_fields_derive_inputs():
    f = one_frame(edit=Note, submit=save)
    assert f["submit"] == {"label": "Do one thing", "handler": "save"}
    assert [(c["field"], c["from"], c["affordances"]) for c in f["components"]] == [
        ("Note.text", "edit", ["write"]),
        ("Note.volume", "edit", ["adjust"]),
        ("Note.secret", "edit", ["write"]),
    ]


def test_shown_fields_derive_reading_and_collections():
    f = one_frame(shows=Basket)
    title, items = f["components"]
    assert (title["field"], title["affordances"]) == ("Basket.title", ["read"])
    assert items["affordances"] == ["read", "press", "scroll"]
    assert [c["field"] for c in items["item"]["components"]] == ["Item.name", "Item.price"]
    assert items["item"]["states"] == ["Item.done"]


def test_edited_lists_are_editable():
    class Stage(__import__("enum").Enum):
        A = "a"

    class Line(vt.Record):
        product: str
        quantity: int = vt.Field(ge=1)

    class Order(vt.Record):
        lines: list[Line] = vt.Field(min_items=1)
        stages: list[Stage]
        watchers: list[Item]
        found: list[Item] = vt.Field(select=vt.jump("item", item_id=Item.id))

    async def place(ctx, o: Order):
        return vt.stay()

    lines, stages, watchers, found = one_frame(edit=Order, submit=place)["components"]
    assert lines["affordances"] == ["move", "add", "remove", "scroll"] and lines["min_items"] == 1
    assert [c["affordances"] for c in lines["item"]["components"]] == [["write"], ["write"]]
    assert (stages["affordances"], stages["many"]) == (["choose"], True)
    assert (watchers["affordances"], watchers["many"]) == (["choose"], True)  # records with an Id are references
    assert found["affordances"] == ["read", "press", "scroll"] and "many" not in found  # a list to navigate
    assert [c["affordances"] for c in watchers["item"]["components"]] == [["read"], ["read"]]


def test_record_identity_is_marked():
    intent = vt.app("t", entry="a", tapes=[vt.tape("a", [vt.frame("See a basket", shows=Basket)]),
                                           vt.tape("item", [vt.frame("x")])]).intent()  # fmt: skip
    assert intent["records"]["Item"]["x-vt"] == {"type": "record", "id": "id"}
    assert intent["records"]["Basket"]["x-vt"] == {"type": "record"}


def test_a_list_shown_directly_is_wrapped():
    f = one_frame(shows=list[Item])
    assert f["shows"] == {"collection": "Item"}
    (wrapper,) = f["components"]
    assert wrapper["type"] == "collection" and wrapper["item"]["record"] == "Item"


def test_explicit_components_come_first_and_override_derived_ones():
    f = one_frame(shows=Basket, components=[
        vt.text(vt.t("basket.intro"), role="supporting"),
        vt.show(Item.price, role="heading"),
        vt.show(Item.sku),
    ])  # fmt: skip
    intro, sku, *derived = f["components"]
    assert intro == {"text": {"t": "basket.intro"}, "role": "supporting", "affordances": ["read"]}
    assert sku["field"] == "Item.sku" and sku["override"] is True
    price = derived[1]["item"]["components"][1]
    assert price["role"] == "heading" and price["override"] is True


def test_a_press_makes_a_shown_value_a_control():
    f = one_frame(shows=Basket, components=[vt.show(Basket.title, press=vt.jump("item"))])
    title = f["components"][0]
    assert title["affordances"] == ["read", "press"]
    assert title["press"] == {"type": "jump", "tape": "item"}


def test_actions():
    async def remove(ctx, item: Item):
        return vt.stay()

    f = one_frame(shows=Basket, actions=[
        vt.action("Remove", remove, on=Item, gesture="swipe-trailing", hidden=Item.done),
        vt.action(Basket.title, vt.back(), role="secondary", key="b"),
    ])  # fmt: skip
    assert f["actions"] == [
        {"label": "Remove", "target": {"handler": "remove"}, "affordance": "press", "on": "Item",
         "gesture": "swipe-trailing", "hidden": {"field": "Item.done"}},
        {"label": {"field": "Basket.title"}, "target": {"type": "back"}, "affordance": "press",
         "key": "b", "role": "secondary"},
    ]  # fmt: skip


def test_identity_and_arguments_on_outcomes():
    assert vt.jump("ws", user="u", sign_in="u1").to_json() == {
        "type": "jump", "tape": "ws", "args": {"user": "u"}, "sign_in": "u1"}  # fmt: skip
    assert vt.back(sign_out=True).to_json() == {"type": "back", "sign_out": True}
    assert vt.download("a.csv", b"x,y").to_json()["encoding"] == "base64"
    assert vt.done(Item).to_json() == {"type": "done", "result": {"item": "Item"}}
    assert vt.copy(Item.name).to_json() == {"type": "copy", "field": "Item.name"}


# ── edges ────────────────────────────────────────────────────────────────────


def test_static_edges():
    intent = load_sample("crm").app.intent()
    edges = {(e["from"].split("/")[0], e["type"], e.get("to", "").split("/")[0], json.dumps(e["via"])) for e in intent["edges"]}
    assert ("deals", "jump", "new_deal", '{"action": "New deal"}') in edges
    assert ("deals", "jump", "deal", '{"select": "Pipeline.deals"}') in edges
    assert ("new_deal", "call", "pick_company", '{"pick": "Deal.company"}') in edges
    assert ("pick_company", "done", "", '{"action": "Choose", "on": "Company"}') in edges


def test_hub_edges_are_implied_not_listed():
    built = build(load_sample("relay").app)
    assert not any(e["type"] == "hub" for e in built.intent["edges"])
    hub = [e for e in built.edges if e.type == "hub"]
    assert len(hub) == len(built.intent["tapes"]) * 3  # one frame per tape, three destinations


def test_timers_and_media_events_are_uses():
    intent = load_sample("pinhole").app.intent()
    stories = next(t for t in intent["tapes"] if t["id"] == "stories")["frames"][0]
    assert stories["after"] == {"seconds": 5, "then": {"handler": "next_story"}}
    watch = next(t for t in load_sample("screening").app.intent()["tapes"] if t["id"] == "watch")["frames"][0]
    assert watch["components"][0]["events"] == {"ended": {"handler": "play_next"}}


# ── builders check what they are given ───────────────────────────────────────


@pytest.mark.parametrize("make, error", [
    (lambda: vt.frame(""), TypeError),
    (lambda: vt.frame("x", id="1st"), ValueError),
    (lambda: vt.frame("x", shows=dict), TypeError),
    (lambda: vt.frame("x", address="c/{id}"), ValueError),
    (lambda: vt.frame("x", components=["Hello"]), TypeError),
    (lambda: vt.frame("x", on_change={"q": save}), TypeError),
    (lambda: vt.frame("x", submit=vt.action("Go", vt.back())), TypeError),
    (lambda: vt.show("Deal.amount"), TypeError),
    (lambda: vt.show(Item.name, colour="red"), TypeError),
    (lambda: vt.action("Go", "login"), TypeError),
    (lambda: vt.action("Go", vt.back(), hidden=True), TypeError),
    (lambda: vt.action("Go", vt.back(), role="big"), ValueError),
    (lambda: vt.action("Go", vt.back(), to=str), TypeError),
    (lambda: vt.tape("a", []), ValueError),
    (lambda: vt.tape("a b", [vt.frame("x")]), ValueError),
    (lambda: vt.app("x", entry="a", tapes=["a"]), TypeError),
    (lambda: vt.after(seconds=0, then=vt.back()), ValueError),
    (lambda: vt.hub([]), TypeError),
    (lambda: vt.Jump[3], TypeError),
])  # fmt: skip
def test_builders_reject_what_they_cannot_hold(make, error):
    with pytest.raises(error):
        make()


def test_a_frame_belongs_to_one_tape():
    f = vt.frame("x")
    vt.tape("a", [f])
    with pytest.raises(ValueError, match="already in tape"):
        vt.tape("b", [f])
