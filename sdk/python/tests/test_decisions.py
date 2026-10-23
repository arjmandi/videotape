import asyncio
from enum import Enum

import pytest
from conftest import load_sample
from pydantic import ValidationError

import videotape as vt
from videotape.decisions import Declared, read


class Stage(Enum):
    LEAD = "lead"
    WON = "won"


class Deal(vt.Record):
    id: str = vt.Field(show=False)
    stage: Stage


def run(coro):
    return asyncio.run(coro)


def declared(fn):
    outcomes, problem = read(fn).declared
    return [d.to_json() for d in outcomes], problem


# ── return types are edges ───────────────────────────────────────────────────


def test_each_outcome_type_reads():
    async def a(ctx) -> vt.Jump["dashboard"]: ...
    async def b(ctx) -> vt.Jump["dashboard"] | vt.Goto["verify"]: ...
    async def c(ctx) -> vt.Stay: ...
    async def d(ctx) -> vt.Back | vt.Done | vt.Open | vt.Download: ...
    async def e(ctx) -> vt.Call["pick_company"]: ...

    assert declared(a) == ([{"type": "jump", "tape": "dashboard"}], None)
    assert declared(b) == ([{"type": "jump", "tape": "dashboard"}, {"type": "goto", "frame": "verify"}], None)
    assert declared(c) == ([{"type": "stay"}], None)
    assert declared(d) == ([{"type": "back"}, {"type": "done"}, {"type": "open"}, {"type": "download"}], None)
    assert declared(e) == ([{"type": "call", "tape": "pick_company"}], None)


def test_postponed_annotations_and_forward_references():
    import future_handlers as m

    assert declared(m.confirm)[0] == [
        {"type": "goto", "frame": "done"}, {"type": "jump", "tape": "orders"}, {"type": "back"}]  # fmt: skip
    assert declared(m.pick)[0] == [{"type": "call", "tape": "pick_address"}]
    assert read(m.confirm).params[0].record is m.Order
    _, problem = declared(m.nameless)
    assert "NameError" in problem and "Missing" in problem


def test_every_handler_has_an_implied_stay():
    async def a(ctx) -> vt.Jump["dashboard"]: ...
    async def b(ctx) -> vt.Stay | vt.Back: ...

    assert read(a).outcomes == [Declared("jump", "dashboard"), Declared("stay", implied=True)]
    assert read(b).outcomes == [Declared("stay"), Declared("back")]


@pytest.mark.parametrize("annotation, words", [
    ("", "no return type"),
    ("-> None", "not an outcome"),
    ("-> str", "not an outcome"),
    ("-> vt.Jump", "without the tape"),
    ("-> vt.Goto | vt.Stay", "without the frame"),
])  # fmt: skip
def test_unreadable_return_types_say_why(annotation, words):
    scope = {"vt": vt}
    exec(f"async def h(ctx) {annotation}: ...", scope)
    outcomes, problem = declared(scope["h"])
    assert outcomes == [] and words in problem
    assert read(scope["h"]).handler_json()["unreadable"] == problem


def test_a_handler_takes_ctx_first():
    async def h(*, d: Deal) -> vt.Stay: ...

    assert "ctx" in declared(h)[1]


# ── parameters are documents ─────────────────────────────────────────────────


def test_parameters_are_documents_by_record_type():
    async def move(ctx, deal: Deal, to: Stage) -> vt.Stay: ...

    deal, to = read(move).params
    assert (deal.name, deal.record, to.record) == ("deal", Deal, None)
    assert to.kind.to_json() == {"type": "choice", "enum": "Stage"}
    assert read(move).handler_json()["params"] == [
        {"name": "deal", "type": "record", "record": "Deal", "required": True},
        {"name": "to", "type": "choice", "enum": "Stage", "required": True},
    ]


def test_loaders_take_arguments_by_name():
    async def load_page(ctx, page: str = "intro") -> Deal: ...

    assert read(load_page).loader_json() == {
        "params": [{"name": "page", "type": "string", "required": False, "default": "intro"}],
        "returns": {"type": "record", "record": "Deal"},
    }


def test_handlers_in_the_intent():
    intent = load_sample("hello").app.intent()
    assert intent["handlers"]["sign_in"] == {
        "params": [{"name": "c", "type": "record", "record": "Credentials", "required": True}],
        "outcomes": [{"type": "jump", "tape": "workspace"}, {"type": "stay", "implied": True}],
    }
    assert {"from": "login/sign-in", "to": "workspace/overview", "type": "jump", "tape": "workspace",
            "via": {"submit": "Sign in", "handler": "sign_in"}} in intent["edges"]  # fmt: skip
    assert {"from": "reset/ask", "to": "reset/sent", "type": "goto", "frame": "sent",
            "via": {"submit": "Reset your password", "handler": "request_reset"}} in intent["edges"]  # fmt: skip


def test_loaders_in_the_intent():
    intent = load_sample("relay").app.intent()
    assert intent["loaders"]["older_messages"]["returns"] == {
        "type": "page", "item": {"type": "record", "record": "Message"}}  # fmt: skip
    assert intent["loaders"]["older_messages"]["params"][0] == {
        "name": "cursor", "type": "string", "nullable": True, "required": True}  # fmt: skip


# ── invoke ───────────────────────────────────────────────────────────────────


def test_invoke_turns_a_return_into_an_outcome_record():
    m = load_sample("hello")
    ctx = vt.Context()
    outcome = run(vt.invoke(m.sign_in, ctx, c={"username": "ada@example.com", "password": "correct horse"}))
    assert outcome == {"type": "jump", "tape": "workspace", "args": {"user": {"id": "u1", "first_name": "Ada"}},
                       "sign_in": "u1"}  # fmt: skip


def test_invoke_turns_reject_into_an_outcome_record():
    m = load_sample("hello")
    c = m.Credentials(username="ada@example.com", password="nope")
    outcome = run(vt.invoke(m.sign_in, vt.Context(), c=c))
    assert outcome == {"type": "reject", "message": "That email and password do not match."}


def test_reject_carries_a_phrase():
    async def h(ctx) -> vt.Stay:
        raise vt.Reject(vt.t("errors.taken", name="ada"))

    assert run(vt.invoke(h, None)) == {"type": "reject", "message": {"t": "errors.taken", "params": {"name": "ada"}}}


def test_invoke_validates_documents_against_their_records():
    async def move(ctx, deal: Deal, to: Stage) -> vt.Stay:
        deal.stage = to
        return vt.stay()

    assert run(vt.invoke(move, None, deal={"id": "d1", "stage": "lead"}, to="won")) == {"type": "stay"}
    with pytest.raises(ValidationError):
        run(vt.invoke(move, None, deal={"id": "d1", "stage": "nope"}, to="won"))
    with pytest.raises(TypeError, match="needs to"):
        run(vt.invoke(move, None, deal={"id": "d1", "stage": "lead"}))
    with pytest.raises(TypeError, match="no parameter colour"):
        run(vt.invoke(move, None, deal={"id": "d1", "stage": "lead"}, to="won", colour="red"))


def test_invoke_refuses_an_outcome_the_return_type_does_not_declare():
    async def h(ctx) -> vt.Jump["dashboard"]:
        return vt.jump("settings")

    async def g(ctx) -> vt.Jump["dashboard"]:
        return "dashboard"

    async def s(ctx) -> vt.Jump["dashboard"]:
        return vt.stay()  # the implied Stay

    with pytest.raises(vt.UndeclaredOutcome, match="jump\\[dashboard\\]"):
        run(vt.invoke(h, None))
    with pytest.raises(vt.UndeclaredOutcome, match="not an outcome"):
        run(vt.invoke(g, None))
    assert run(vt.invoke(s, None)) == {"type": "stay"}


def test_invoke_refuses_a_handler_whose_edges_are_unknown():
    async def h(ctx):
        return vt.stay()

    with pytest.raises(TypeError, match="no return type"):
        run(vt.invoke(h, None))


def test_invoke_calls_plain_functions_too():
    def h(ctx) -> vt.Download:
        return vt.download("a.txt", "hi")

    assert run(vt.invoke(h, None)) == {"type": "download", "name": "a.txt", "data": "hi"}
