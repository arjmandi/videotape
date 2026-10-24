"""vt.Draft[X]: a handler that sees the edited document unfinished (05 §6.1, Q75)."""

import videotape as vt
from test_serve import play

SAVED: list[dict] = []


class Note(vt.Record):
    title: str
    body: str = vt.Field("", commit="change")


async def save_draft(ctx, note: vt.Draft[Note]):
    SAVED.append({"title": note.title, "body": note.body, "problems": note.problems})
    note.body = note.body.strip()
    return vt.stay()


async def save_note(ctx, note: Note):
    return vt.stay()


def app_with(handler):
    return vt.app("notes", entry="t", tapes=[vt.tape("t", [vt.frame("Write", edit=Note, on_change={Note.body: handler})])])


NOTE = {"record": "Note", "local": "d1"}


def decide(e, id, handler, value=None, version=0):
    entry = {"ref": NOTE, "version": version, **({"value": value} if value is not None else {})}
    return e.ask({"t": "decide", "id": id, "handler": handler, "session": "s1", "user": None, "documents": {"note": entry}})


def test_a_draft_has_the_same_fields_all_optional_and_keeps_their_defaults():
    draft = vt.Draft[Note]()
    assert (draft.title, draft.body, draft.problems) == (None, "", {})
    assert isinstance(draft, Note) and vt.Draft[Note] is vt.Draft[Note]


def test_a_draft_parameter_is_in_the_intent_and_checks_clean():
    intent = app_with(save_draft).intent()
    assert intent["handlers"]["save_draft"]["params"] == [{"name": "note", "type": "draft", "record": "Note", "required": True}]
    assert [d.code for d in app_with(save_draft).check() if d.level == "error"] == []

    class Other(vt.Record):
        x: str

    async def wrong(ctx, other: vt.Draft[Other]):
        return vt.stay()

    errors = [d for d in app_with(wrong).check() if d.level == "error"]
    assert [d.code for d in errors] == ["unknown-document"]
    assert "vt.Draft[Other], but this frame does not edit Other" in errors[0].message


def test_a_draft_is_saved_while_a_required_field_is_still_empty():
    SAVED.clear()

    async def body(e):
        result = await decide(e, "1", "save_draft", {"body": "  half a thought "})
        return result, [m for m in e.out if m["t"] == "sync"]

    result, syncs = play(app_with(save_draft), body)
    assert result["outcome"] == {"type": "stay"}
    assert SAVED == [{"title": None, "body": "  half a thought ", "problems": {"title": ["Field required"]}}]
    assert syncs[0]["changes"][0]["ops"] == [{"op": "set", "path": ["body"], "value": "half a thought"}]


def test_a_handler_that_takes_the_record_by_its_type_is_told_it_is_not_complete():
    async def body(e):
        return await decide(e, "1", "save_note", {"body": "x"})

    error = play(app_with(save_note), body)["error"]
    assert error["type"] == "IncompleteRecord"
    assert "Note is not complete yet (title: Field required)" in error["message"]
    assert "vt.Draft[Note]" in error["message"]


def test_the_mirror_holds_an_unfinished_document_as_a_draft_until_it_validates():
    async def body(e):
        await decide(e, "1", "save_draft", {"body": "x"})
        copy = e.client.mirror.get(NOTE)
        assert copy.obj.problems == {"title": ["Field required"]}
        e.client.receive({"t": "sync", "changes": [{"doc": NOTE, "from": 0, "version": 1, "ops": [{"op": "set", "path": ["title"], "value": "Plan"}]}]})
        complete = e.client.mirror.get(NOTE).obj
        assert type(complete) is Note and complete.title == "Plan"
        return await decide(e, "2", "save_note", version=1)

    assert play(vt.app("notes", entry="t", tapes=[vt.tape("t", [vt.frame("Write", edit=Note, on_change={Note.body: save_draft},
                                                                         actions=[vt.action("Save", save_note)])])]), body)["outcome"] == {"type": "stay"}
