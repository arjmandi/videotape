from datetime import date, datetime
from decimal import Decimal
from enum import Enum

import pytest
from pydantic import ValidationError

import videotape as vt
from videotape.records import fields_of, kind_of, records_in


class Stage(Enum):
    LEAD = "lead"
    WON = "won"


class Company(vt.Record):
    id: vt.Id
    name: str


class User(vt.Record):
    id: vt.Id
    name: str


def team() -> list[User]:
    return []


class Deal(vt.Record):
    id: vt.Id
    name: str = vt.Field(role="heading")
    company: Company = vt.pick("pick_company")
    amount: vt.Money = vt.Field(ge=0)
    stage: Stage
    close: date | None = vt.Field(group="dates")
    owner: User = vt.Field(group="people", options=team)
    notes: vt.Text | None = vt.Field(lines=(3, 12), importance="optional")
    starred: bool = vt.State(False)


class Pipeline(vt.Record):
    id: vt.Id
    deals: list[Deal] = vt.Field(group_by=Deal.stage, select=None)


def a_deal(**over):
    values = dict(
        id="d1", name="Acme renewal", company=Company(id="c1", name="Acme"),
        amount={"amount": "1200.00", "currency": "EUR"}, stage=Stage.LEAD, owner=User(id="u1", name="Ada"),
    )  # fmt: skip
    return Deal(**{**values, **over})


# ── field references ─────────────────────────────────────────────────────────


def test_a_field_on_the_class_is_a_reference():
    ref = Deal.amount
    assert isinstance(ref, vt.FieldRef)
    assert (ref.record, ref.name, str(ref)) == (Deal, "amount", "Deal.amount")
    assert ref.to_json() == {"field": "Deal.amount"}


def test_references_are_values():
    assert Deal.amount == Deal.amount
    assert {Deal.stage: 1}[Deal.stage] == 1
    assert Deal.amount != Deal.stage


def test_records_have_no_implicit_id():
    assert str(Pipeline.id) == "Pipeline.id"

    class Draft(vt.Record):
        text: vt.Text = ""

    assert "id" not in Draft.model_fields


def test_unknown_attributes_still_raise():
    with pytest.raises(AttributeError):
        Deal.nothing  # noqa: B018
    assert callable(Deal.model_validate)


def test_instances_hold_values_not_references():
    d = a_deal()
    assert d.name == "Acme renewal"
    assert d.amount == vt.Money("1200", "EUR")


# ── `| None` is not required ─────────────────────────────────────────────────


def test_optional_fields_default_to_none():
    d = a_deal()
    assert d.close is None and d.notes is None
    required = {f.name for f in fields_of(Deal) if f.required}
    assert required == {"name", "company", "amount", "stage", "owner"}


def test_optional_fields_with_postponed_annotations_and_forward_references():
    from forward_records import Deal as FDeal
    from forward_records import User as FUser

    d = FDeal(id="d1", name="x")
    assert (d.owner, d.notes, d.tags) == (None, None, None)
    d.owner = FUser(id="u", name="Ada")
    kinds = {f.name: f.kind.to_json() for f in fields_of(FDeal)}
    assert kinds["owner"] == {"type": "record", "record": "User", "nullable": True}
    assert kinds["notes"] == {"type": "text", "lines": [3, 12], "nullable": True}


# ── values ───────────────────────────────────────────────────────────────────


def test_secret_is_a_string_with_a_masked_repr():
    class Credentials(vt.Record):
        username: str
        password: vt.Secret

    c = Credentials(username="ada", password="hunter2")
    assert isinstance(c.password, vt.Secret) and c.password == "hunter2"
    assert "hunter2" not in repr(c)
    schema = Credentials.model_json_schema()["properties"]["password"]
    assert schema["format"] == "password" and schema["x-vt"] == {"type": "secret"}


def test_money_carries_its_currency_and_takes_constraints():
    assert a_deal(amount="12.50 EUR").amount == vt.Money("12.50", "EUR")
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        a_deal(amount={"amount": "-1", "currency": "EUR"})
    with pytest.raises(ValidationError):
        a_deal(amount={"amount": "1", "currency": "euro"})
    assert a_deal().model_dump(mode="json")["amount"] == {"amount": "1200.00", "currency": "EUR"}
    assert vt.Money("1", "EUR") >= 0 and vt.Money("1", "EUR") < Decimal("2")


def test_image_carries_alt_text():
    with pytest.raises(ValidationError):
        vt.Image(src="https://x/a.jpg")
    assert vt.Image(src="https://x/a.jpg", alt="A lake").alt == "A lake"


def test_rich_text_from_a_string_and_from_markdown():
    assert vt.RichText.model_validate("one\n\ntwo").plain == "one\n\ntwo"
    md = vt.RichText.from_markdown("Hello *there*, see [docs](https://d) and @ada.\n\n- one\n- `two`\n\n```py\nx = 1\n```")
    para, lst, code = md.blocks
    assert [(s.text, s.emphasis, s.link, s.mention) for s in para.spans] == [
        ("Hello ", None, None, None), ("there", "em", None, None), (", see ", None, None, None),
        ("docs", None, "https://d", None), (" and ", None, None, None), ("@ada", None, None, "ada"),
        (".", None, None, None),
    ]  # fmt: skip
    assert [[s.text for s in item] for item in lst.items] == [["one"], ["two"]]
    assert (code.text, code.language) == ("x = 1", "py")
    assert md.plain.startswith("Hello there, see docs and @ada.")


def test_series_takes_rows_positionally_and_checks_columns():
    s = vt.Series([{"week": 1, "events": 3}], x="week", y="events")
    assert s.rows[0]["events"] == 3
    with pytest.raises(ValidationError, match="row 0 has no events"):
        vt.Series([{"week": 1}], x="week", y="events")


def test_page_is_generic():
    page = vt.Page[Company]([{"id": "c1", "name": "Acme"}], next="c2")
    assert page.items[0].name == "Acme" and page.next == "c2"


def test_t_is_a_phrase():
    p = vt.t("dashboard.hello", name="Ada")
    assert (p.key, p.params, str(p)) == ("dashboard.hello", {"name": "Ada"}, "dashboard.hello")
    with pytest.raises(ValueError):
        vt.t("not a key")


# ── options ──────────────────────────────────────────────────────────────────


def test_options_travel_in_json_schema_as_x_vt():
    props = Deal.model_json_schema()["properties"]
    assert props["name"]["x-vt"] == {"role": "heading"}
    assert props["company"]["x-vt"] == {"pick": "pick_company"}
    assert props["owner"]["x-vt"] == {"group": "people", "options": {"loader": "team"}}
    assert props["starred"]["x-vt"] == {"state": True}
    assert props["notes"]["x-vt"] == {"lines": [3, 12], "importance": "optional"}
    assert Pipeline.model_json_schema()["properties"]["deals"]["x-vt"] == {"group_by": {"field": "Deal.stage"}}


def test_options_are_checked_where_they_are_written():
    with pytest.raises(ValueError, match="role='title'"):
        vt.Field(role="title")
    with pytest.raises(TypeError, match="never an expression"):
        vt.Field(hidden=True)
    with pytest.raises(TypeError, match="@vt.pages"):
        vt.Field(pages="feed_page")
    with pytest.raises(ValueError, match="lines"):
        vt.Field(lines=(6, 1))


def test_kinds():
    kinds = {f.name: f.kind.to_json() for f in fields_of(Deal)}
    assert kinds == {
        "id": {"type": "id"},
        "name": {"type": "string"},
        "company": {"type": "record", "record": "Company"},
        "amount": {"type": "money"},
        "stage": {"type": "choice", "enum": "Stage"},
        "close": {"type": "date", "nullable": True},
        "owner": {"type": "record", "record": "User"},
        "notes": {"type": "text", "lines": [3, 12], "nullable": True},
        "starred": {"type": "boolean"},
    }
    assert kind_of(list[Deal]).to_json() == {"type": "collection", "item": {"type": "record", "record": "Deal"}}
    assert kind_of(datetime).type == "datetime"
    assert kind_of(vt.Video | None).type == "video"


def test_constraints_and_states_are_read():
    specs = {f.name: f for f in fields_of(Deal)}
    assert specs["amount"].constraints == {"ge": 0}
    assert specs["starred"].state and not specs["starred"].shown
    assert not specs["id"].shown and specs["name"].shown
    assert specs["notes"].options["lines"] == (3, 12)


def test_records_in_walks_nested_records():
    assert records_in(Pipeline) == [Pipeline, Deal, Company, User]


def test_update_merges_fields():
    d = a_deal()
    d.update({"name": "Renewal"}, stage=Stage.WON)
    assert (d.name, d.stage) == ("Renewal", Stage.WON)
    with pytest.raises(ValidationError):
        d.update(stage="nope")


# ── identity, text, lists, copy, pages ───────────────────────────────────────


def test_an_id_is_never_shown_and_not_required_until_saved():
    unsaved = {k: v for k, v in a_deal().model_dump().items() if k != "id"}
    assert Deal(**unsaved).id is None
    assert Deal(**{**a_deal().model_dump(), "id": 7}).id == "7"
    spec = next(f for f in fields_of(Deal) if f.name == "id")
    assert (spec.kind.type, spec.required, spec.shown) == ("id", False, False)
    assert Deal.model_json_schema()["properties"]["id"]["x-vt"] == {"type": "id"}


def test_a_record_has_one_identity():
    class Twice(vt.Record):
        a: vt.Id
        b: vt.Id

    with pytest.raises(vt.RecordError, match="2 vt.Id fields"):
        fields_of(Twice)


def test_text_is_a_type_with_one_to_six_lines_unless_lines_says_otherwise():
    class Draft(vt.Record):
        text: vt.Text = ""
        notes: vt.Text = vt.Field("", lines=4)

    kinds = {f.name: f.kind.to_json() for f in fields_of(Draft)}
    assert kinds == {"text": {"type": "text", "lines": [1, 6]}, "notes": {"type": "text", "lines": [4, 4]}}
    assert Draft(text="hi").text == "hi"
    with pytest.raises(TypeError):
        vt.Text(lines=(1, 6))


def test_options_on_the_wrong_type_make_the_record_unreadable():
    class Wrong(vt.Record):
        name: str = vt.Field(lines=3)

    class Bounded(vt.Record):
        name: str = vt.Field(min_items=1)

    with pytest.raises(vt.RecordError, match="lines= is for vt.Text"):
        fields_of(Wrong)
    with pytest.raises(vt.RecordError, match="min_items= is for lists"):
        fields_of(Bounded)


def test_list_bounds_are_options_and_constraints():
    class Order(vt.Record):
        lines: list[str] = vt.Field(min_items=1, max_items=2)

    assert Order.model_json_schema()["properties"]["lines"]["minItems"] == 1
    with pytest.raises(ValidationError):
        Order(lines=[])
    with pytest.raises(ValidationError):
        Order(lines=["a", "b", "c"])
    spec = fields_of(Order)[0]
    assert spec.to_json() == {"type": "collection", "item": {"type": "string"}, "min_items": 1, "max_items": 2}


def test_a_record_refuses_copy():
    with pytest.raises(ValidationError, match="copy, which lives in intent"):
        Company(name=vt.t("company.default"))
    c = Company(name="Acme")
    with pytest.raises(ValidationError, match="copy"):
        c.name = vt.t("company.default")

    class Tags(vt.Record):
        tags: list[str]

    with pytest.raises(ValidationError, match="copy"):
        Tags(tags=["plain", vt.t("tag.new")])


def test_t_takes_field_references_as_parameters():
    from videotape._encode import encode

    assert encode(vt.t("deal.title", name=Deal.name)) == {"t": "deal.title", "params": {"name": {"field": "Deal.name"}}}


def test_pages_registers_a_loader_after_its_record():
    class Feed(vt.Record):
        id: vt.Id
        posts: list[Company]

    @vt.pages(Feed.posts)
    async def feed_page(ctx, cursor: str | None) -> vt.Page[Company]: ...

    spec = next(f for f in fields_of(Feed) if f.name == "posts")
    assert spec.pages is feed_page
    assert spec.to_json()["pages"] == {"loader": "feed_page"}
    with pytest.raises(ValueError, match="already has a pages loader"):
        vt.pages(Feed.posts)(lambda ctx, cursor: None)
    with pytest.raises(TypeError):
        vt.pages("Feed.posts")


def test_page_takes_items_and_next_positionally():
    page = vt.Page(*([Company(id="c1", name="Acme")], "c2"))
    assert page.next == "c2" and page.items[0].name == "Acme"
