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
    id: vt.Id
    stage: Stage


class User(vt.Record):
    id: vt.Id
    name: str


def run(coro):
    return asyncio.run(coro)


def declared(fn):
    outcomes, problem = read(fn).declared
    return [d.to_json() for d in outcomes], problem


# ── edges are read from the body ─────────────────────────────────────────────


def test_each_outcome_reads_from_its_return():
    async def a(ctx):
        return vt.jump("dashboard")

    async def b(ctx, d: Deal):
        if d.stage is Stage.WON:
            return vt.goto("verify")
        return vt.jump("dashboard", deal_id=d.id)

    async def c(ctx):
        return vt.stay()

    async def d(ctx):
        return vt.back() if ctx else vt.done(True)

    async def e(ctx):
        return vt.open("https://example.com")

    async def f(ctx):
        return vt.download("a.csv", "x")

    assert declared(a) == ([{"type": "jump", "tape": "dashboard"}], None)
    assert declared(b) == ([{"type": "goto", "frame": "verify"},
                            {"type": "jump", "tape": "dashboard", "args": ["deal_id"]}], None)  # fmt: skip
    assert declared(c) == ([{"type": "stay"}], None)
    assert declared(d) == ([{"type": "back"}, {"type": "done"}], None)
    assert declared(e) == ([{"type": "open"}], None)
    assert declared(f) == ([{"type": "download"}], None)


def test_sign_in_and_sign_out_reset_history():
    async def a(ctx, user: User):
        return vt.jump("dashboard", sign_in=user)

    async def b(ctx):
        return vt.jump("landing", sign_out=True)

    async def c(ctx):
        return vt.jump("landing", sign_out=False)

    assert declared(a)[0] == [{"type": "jump", "tape": "dashboard", "resets_history": True, "signs_in": True}]
    assert declared(b)[0] == [{"type": "jump", "tape": "landing", "resets_history": True}]
    assert declared(c)[0] == [{"type": "jump", "tape": "landing"}]


def test_calls_name_their_continuation():
    async def picked(ctx, result: str):
        return vt.stay()

    async def ask(ctx):
        return vt.call("pick_address", then=picked, kind="home")

    (call,), _ = read(ask).declared
    assert (call.type, call.target, call.args, call.then) == ("call", "pick_address", ("kind",), picked)
    assert call.to_json() == {"type": "call", "tape": "pick_address", "args": ["kind"], "then": {"handler": "picked"}}


def test_splatted_arguments_are_open():
    async def a(ctx):
        args = {"page": 2}
        return vt.jump("orders", **args)

    assert declared(a)[0] == [{"type": "jump", "tape": "orders", "args_open": True}]


def test_postponed_annotations_and_forward_references():
    import future_handlers as m

    assert declared(m.confirm)[0] == [
        {"type": "goto", "frame": "done"}, {"type": "jump", "tape": "orders", "args": ["order_id"]}, {"type": "back"}]  # fmt: skip
    (call,), _ = read(m.pick).declared
    assert call.then is m.address_picked
    assert read(m.confirm).params[0].record is m.Order
    _, problem = declared(m.nameless)
    assert "NameError" in problem and "Missing" in problem


def test_videotape_under_any_name():
    import aliased_handlers as m

    assert declared(m.a) == ([{"type": "jump", "tape": "orders", "args": ["page"]}], None)
    assert declared(m.b) == ([{"type": "stay"}, {"type": "back"}], None)
    assert declared(m.f) == ([{"type": "open"}], None)  # a nested function's return is its own


def test_unreadable_returns_say_where_and_ask_for_outcomes():
    import aliased_handlers as m

    _, problem = declared(m.c)
    assert "line 21 returns helper(...)" in problem and "@vt.outcomes" in problem
    _, problem = declared(m.e)
    assert "line 31 names the tape of vt.jump(...) with where, a local variable" in problem
    assert read(m.e).handler_json()["unreadable"] == problem


def test_outcomes_declares_what_the_body_cannot_say():
    import aliased_handlers as m

    assert declared(m.d) == ([{"type": "jump", "tape": "orders", "args": ["page"]}], None)
    with pytest.raises(TypeError):
        vt.outcomes("dashboard")
    with pytest.raises(TypeError):
        vt.outcomes()


@pytest.mark.parametrize("body, words", [
    ("return None", "returns nothing"),
    ("return 'dashboard'", "returns 'dashboard', which is not an outcome"),
    ("pass", "returns no outcome"),
])  # fmt: skip
def test_bodies_without_outcomes_say_why(body, words, tmp_path, monkeypatch):
    source = f"import videotape as vt\n\n\nasync def h(ctx):\n    {body}\n"
    (tmp_path / "bodies.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib

    module = importlib.import_module("bodies")
    importlib.reload(module)
    outcomes, problem = declared(module.h)
    assert outcomes == [] and words in problem


def test_a_handler_without_source_needs_outcomes():
    scope = {"vt": vt}
    exec("async def h(ctx):\n    return vt.stay()", scope)
    assert declared(scope["h"]) == ([], "its source cannot be read; declare its outcomes with @vt.outcomes(...)")
    marked = vt.outcomes(vt.stay())(scope["h"])
    read.__globals__["_cache"].pop(marked, None)
    assert declared(marked) == ([{"type": "stay"}], None)


def test_annotations_are_no_longer_edges():
    with pytest.raises(TypeError):
        vt.Jump["dashboard"]  # noqa: B018


def test_every_handler_has_an_implied_stay():
    async def a(ctx):
        return vt.jump("dashboard")

    async def b(ctx):
        return vt.stay() if ctx else vt.back()

    assert read(a).outcomes == [Declared("jump", "dashboard"), Declared("stay", implied=True)]
    assert read(b).outcomes == [Declared("stay"), Declared("back")]


def test_a_handler_takes_ctx_first():
    async def h(*, d: Deal):
        return vt.stay()

    assert "ctx" in declared(h)[1]


# ── parameters are documents ─────────────────────────────────────────────────


def test_parameters_are_documents_by_record_type():
    async def move(ctx, deal: Deal, to: Stage):
        return vt.stay()

    deal, to = read(move).params
    assert (deal.name, deal.record, to.record) == ("deal", Deal, None)
    assert read(move).handler_json()["params"] == [
        {"name": "deal", "type": "record", "record": "Deal", "required": True},
        {"name": "to", "type": "choice", "enum": "Stage", "required": True},
    ]


def test_loaders_take_arguments_by_name():
    async def load_page(ctx, page: str = "intro") -> Deal: ...

    assert read(load_page).loader_json() == {
        "params": [{"name": "page", "type": "string", "required": False, "default": "intro"}],
        "returns": [{"type": "record", "record": "Deal"}],
    }


def test_handlers_in_the_intent():
    intent = load_sample("hello").app.intent()
    assert intent["handlers"]["sign_in"] == {
        "params": [{"name": "c", "type": "record", "record": "Credentials", "required": True}],
        "outcomes": [{"type": "jump", "tape": "workspace", "resets_history": True, "signs_in": True},
                     {"type": "stay", "implied": True}],
    }
    edges = [e for e in intent["edges"] if e["via"].get("handler")]
    assert [(e["from"], e["to"], e.get("resets_history")) for e in edges] == [
        ("login", "workspace", True), ("reset/ask", "reset/sent", None)]  # fmt: skip


def test_a_continuation_is_used_where_the_call_is_made():
    intent = load_sample("crm").app.intent()
    deal = [e for e in intent["edges"] if e["from"] == "deal"]
    assert {"type": "jump", "tape": "deals", "via": {"then": "confirm_delete", "handler": "delete_confirmed"}}.items() \
        <= next(e for e in deal if e["via"].get("then")).items()
    assert intent["handlers"]["delete_confirmed"]["params"][1] == {"name": "result", "type": "boolean", "required": True}


def test_loaders_in_the_intent():
    intent = load_sample("relay").app.intent()
    assert intent["loaders"]["older_messages"]["returns"] == [
        {"type": "page", "item": {"type": "record", "record": "Message"}}]  # fmt: skip
    assert intent["loaders"]["older_messages"]["params"] == [
        {"name": "conv", "type": "record", "record": "Conversation", "required": True},
        {"name": "cursor", "type": "string", "nullable": True, "required": True},
    ]


# ── invoke ───────────────────────────────────────────────────────────────────


def test_invoke_turns_a_return_into_an_outcome_record():
    m = load_sample("hello")
    outcome = run(vt.invoke(m.sign_in, vt.Context(), c={"username": "ada@example.com", "password": "correct horse"}))
    assert outcome == {"type": "jump", "tape": "workspace", "sign_in": {"id": "u1", "first_name": "Ada"}}


def test_invoke_turns_reject_into_an_outcome_record():
    m = load_sample("hello")
    c = m.Credentials(username="ada@example.com", password="nope")
    outcome = run(vt.invoke(m.sign_in, vt.Context(), c=c))
    assert outcome == {"type": "reject", "message": "That email and password do not match."}


def test_reject_carries_a_phrase():
    async def h(ctx):
        raise vt.Reject(vt.t("errors.taken", name="ada"))
        return vt.stay()

    assert run(vt.invoke(h, None)) == {"type": "reject", "message": {"t": "errors.taken", "params": {"name": "ada"}}}


def test_sign_in_takes_the_users_record():
    async def by_id(ctx):
        return vt.jump("dashboard", sign_in="u1")

    async def unsaved(ctx):
        return vt.jump("dashboard", sign_in=User(name="Ada"))

    with pytest.raises(TypeError, match="the user's record"):
        run(vt.invoke(by_id, None))
    with pytest.raises(TypeError, match="vt.Id set"):
        run(vt.invoke(unsaved, None))


def test_invoke_validates_documents_and_results():
    async def move(ctx, deal: Deal, to: Stage):
        deal.stage = to
        return vt.stay()

    async def confirmed(ctx, deal: Deal, result: bool):
        return vt.jump("deals") if result else vt.stay()

    assert run(vt.invoke(move, None, deal={"id": "d1", "stage": "lead"}, to="won")) == {"type": "stay"}
    assert run(vt.invoke(confirmed, None, deal={"id": "d1", "stage": "lead"}, result=True)) == {"type": "jump", "tape": "deals"}
    with pytest.raises(ValidationError):
        run(vt.invoke(move, None, deal={"id": "d1", "stage": "nope"}, to="won"))
    with pytest.raises(TypeError, match="needs to"):
        run(vt.invoke(move, None, deal={"id": "d1", "stage": "lead"}))
    with pytest.raises(TypeError, match="no parameter colour"):
        run(vt.invoke(move, None, deal={"id": "d1", "stage": "lead"}, to="won", colour="red"))


def test_invoke_refuses_an_outcome_the_body_does_not_show():
    def settings():
        return vt.jump("settings")

    @vt.outcomes(vt.jump("dashboard"))
    async def h(ctx):
        return settings()

    async def s(ctx):
        if ctx:
            return vt.jump("dashboard")
        raise vt.Reject("no")

    with pytest.raises(vt.UndeclaredOutcome, match=r"shows only jump\(dashboard\)"):
        run(vt.invoke(h, None))
    assert run(vt.invoke(s, 1)) == {"type": "jump", "tape": "dashboard"}


def test_invoke_refuses_a_handler_whose_edges_are_unknown():
    def helper():
        return vt.stay()

    async def h(ctx):
        return helper()

    with pytest.raises(TypeError, match="@vt.outcomes"):
        run(vt.invoke(h, None))


def test_invoke_calls_plain_functions_too():
    def h(ctx):
        return vt.download("a.txt", "hi")

    assert run(vt.invoke(h, None)) == {"type": "download", "name": "a.txt", "data": "hi"}


# ── names from the module (Q45) and goto without arguments (Q46) ─────────────


def test_tape_names_resolve_against_the_handlers_module():
    import named_tapes as m

    assert declared(m.by_constant) == ([{"type": "jump", "tape": "dashboard"}], None)
    assert declared(m.by_tape) == ([{"type": "jump", "tape": "dashboard", "args": ["week"]}], None)
    assert declared(m.by_dotted_name) == ([{"type": "call", "tape": "settings"}], None)
    _, problem = declared(m.by_local)
    assert "with DASHBOARD, a local variable" in problem


def test_static_outcomes_take_a_tape_object():
    import named_tapes as m

    assert vt.jump(m.dashboard, week=1).to_json() == {"type": "jump", "tape": "dashboard", "args": {"week": 1}}
    assert vt.call(m.dashboard).to_json() == {"type": "call", "tape": "dashboard"}
    with pytest.raises(TypeError):
        vt.jump(3)


def test_goto_carries_no_arguments():
    import named_tapes as m

    with pytest.raises(TypeError):
        vt.goto("confirm", step=2)
    _, problem = declared(m.goto_with_arguments)
    assert "passes step= to vt.goto(...), which takes no arguments" in problem


async def _resume_off(ctx, c: _ResumeLogin):
    return vt.jump("home", sign_in=_ResumeUser(id="u1"), resume=False)


class _ResumeUser(vt.Record):
    id: vt.Id


class _ResumeLogin(vt.Record):
    name: str


def test_resume_is_reserved_on_identity_outcomes():
    """Q70: `resume=False` on a sign-in lands where the outcome points; the SDK reads it as reserved."""
    out = vt.jump("home", sign_in=_ResumeUser(id="u1"), resume=False).to_json()
    assert out == {"type": "jump", "tape": "home", "sign_in": {"id": "u1"}, "resume": False}
    assert "resume" not in vt.stay(sign_out=True).to_json()
    [declared] = [d for d in read(_resume_off).outcomes if d.type == "jump"]
    assert declared.args == () and declared.signs_in
    with pytest.raises(TypeError, match="resume= takes True or False"):
        vt.goto("x", resume="no")
    app = vt.app("resume", entry="t", tapes=[
        vt.tape("t", [vt.frame("Sign in", edit=_ResumeLogin, submit=_resume_off)]),
        vt.tape("home", [vt.frame("Home", actions=[vt.action("Out", vt.jump("t"))])]),
    ])
    assert [d.code for d in app.check() if d.level == "error"] == []
