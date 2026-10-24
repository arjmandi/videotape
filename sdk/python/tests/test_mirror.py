"""The app's mirror (05 §6.2, Q53, Q54, Q57), against a fake engine."""

import asyncio

import videotape as vt
from conftest import load_sample
from test_serve import ADA, conversation, draft, play
from videotape.tracking import KEY

relay = load_sample("relay")
hello = load_sample("hello")
CONV = {"record": "Conversation", "id": "c1"}
DRAFT = {"record": "Draft", "local": "d1"}


def send(e, id, documents):
    return e.ask({"t": "decide", "id": id, "handler": "send", "session": "s1", "user": ADA, "documents": documents})


def by_ref(conv_version, draft_version):
    return {"conv": {"ref": CONV, "version": conv_version}, "draft": {"ref": DRAFT, "version": draft_version}}


def echo(e, ref, version, count=1):
    """What the engine says after applying the app's own changes: the versions they reached."""
    for _ in range(count):
        e.client.receive({"t": "sync", "changes": [{"doc": ref, "from": version, "version": version + 1, "origin": "app"}]})
        version += 1
    return version


def test_a_document_sent_whole_once_is_named_by_version_after():
    async def body(e):
        await send(e, "1", {"conv": conversation(), "draft": draft(text="one")})
        first = e.client.mirror.get(CONV).obj
        assert len(first.messages) == 2 and e.client.mirror.get(CONV).unacked == 2   # insert, then update
        conv = echo(e, CONV, 0, 2)
        dr = echo(e, DRAFT, 0)
        e.client.receive({"t": "sync", "changes": [{"doc": DRAFT, "from": dr, "version": dr + 1, "ops": [{"op": "set", "path": ["text"], "value": "two"}]}]})
        result = await send(e, "2", by_ref(conv, dr + 1))
        assert result["outcome"] == {"type": "stay"}
        assert e.client.mirror.get(CONV).obj is first and len(first.messages) == 3
        return [m for m in e.out if m["t"] == "sync"]

    syncs = play(relay.app, body)
    inserted = [o for m in syncs for c in m["changes"] for o in c["ops"] if o["op"] == "insert"]
    assert [o["value"]["text"]["blocks"][0]["spans"][0]["text"] for o in inserted] == ["one", "two"]


def test_a_missing_or_stale_copy_is_said_and_nothing_runs():
    async def body(e):
        missing = await send(e, "1", by_ref(0, 0))
        await send(e, "2", {"conv": conversation(), "draft": draft(text="x")})
        behind = await send(e, "3", by_ref(9, 0))
        return missing, behind, [m for m in e.out if m["t"] == "sync"]

    missing, behind, syncs = play(relay.app, body)
    assert missing["stale"] == [{"doc": CONV, "have": None}, {"doc": DRAFT, "have": None}]
    assert behind["stale"] == [{"doc": CONV, "have": 0}]                       # the draft is at 0 here
    assert all(m.get("decision") == "2" for m in syncs)                           # 1 and 3 ran nothing


def test_changes_from_the_engine_keep_the_copy_current():
    async def body(e):
        await send(e, "1", {"conv": conversation(), "draft": draft(text="x")})
        version = echo(e, CONV, 0, 2)
        key = "~e1"
        e.client.receive({"t": "sync", "changes": [{"doc": CONV, "from": version, "version": version + 1, "ops": [
            {"op": "set", "path": ["title"], "value": "Renamed"},
            {"op": "set", "path": ["messages", {"key": key}, "pending"], "value": True},
            {"op": "insert", "path": ["messages"], "key": "~e9", "at": "start",
             "value": {"author": {"id": "u2", "name": "Grace"}, "text": "Earlier.", "sent_at": None, "pending": False}},
        ]}]})
        copy = e.client.mirror.get(CONV)
        assert copy.version == version + 1
        assert copy.obj.title == "Renamed" and copy.obj.messages[1].pending is True
        assert copy.obj.messages[0].text.plain == "Earlier."
        assert [m for m in e.out if m["t"] == "sync"][-1]["decision"] == "1"         # nothing was sent back
        copy.obj.messages[0].pending = True                                          # the inserted item is tracked
        await asyncio.sleep(0)
        last = e.out[-1]
        assert "decision" not in last                                                # outside a decision: confirmed
        assert last["changes"][0]["ops"] == [{"op": "set", "path": ["messages", {"key": "~e9"}, "pending"], "value": True}]
        e.client.receive({"t": "sync", "drop": [CONV]})
        return e.client.mirror.get(CONV)

    assert play(relay.app, body) is None


def test_a_copy_that_does_not_line_up_is_dropped_and_the_engine_told():
    async def body(e):
        await send(e, "1", {"conv": conversation(), "draft": draft(text="x")})
        e.client.receive({"t": "sync", "changes": [{"doc": DRAFT, "from": 5, "version": 6, "ops": [{"op": "set", "path": ["text"], "value": "?"}]}]})
        gap = e.client.mirror.get(DRAFT)
        # A change from elsewhere while the app's own two batches are still in flight: no order to trust.
        e.client.receive({"t": "sync", "changes": [{"doc": CONV, "from": 0, "version": 1, "ops": [{"op": "set", "path": ["title"], "value": "?"}]}]})
        conflict = e.client.mirror.get(CONV)
        return gap, conflict, [m for m in e.out if m["t"] == "forget"]

    gap, conflict, forgets = play(relay.app, body)
    assert gap is None and conflict is None
    assert forgets == [{"t": "forget", "docs": [DRAFT]}, {"t": "forget", "docs": [CONV]}]


def test_records_with_secrets_are_never_mirrored():
    async def body(e):
        creds = {"ref": {"record": "Credentials", "local": "d1"}, "version": 0, "value": {"username": "ada@example.com", "password": "nope"}}
        await e.ask({"t": "decide", "id": "1", "handler": "sign_in", "session": "s1", "user": None, "documents": {"c": creds}})
        return len(e.client.mirror)

    assert play(hello.app, body) == 0


def test_vt_docs_reads_the_copy_and_fetches_one_it_does_not_hold():
    async def body(e):
        await send(e, "1", {"conv": conversation(), "draft": draft(text="x")})
        held = vt.docs[relay.Conversation, "c1"]
        assert held is e.client.mirror.get(CONV).obj and held.title == "Launch"
        pending = asyncio.ensure_future(vt.docs.fetch(relay.Conversation, "c2"))
        await asyncio.sleep(0)
        ask = e.out[-1]
        assert ask == {"t": "fetch", "id": ask["id"], "docs": [{"record": "Conversation", "id": "c2"}]}
        value = {"id": "c2", "title": "Lunch", "typing": None, "messages": []}
        e.client.receive({"t": "fetched", "id": ask["id"], "documents": [{"doc": {"record": "Conversation", "id": "c2"}, "version": 3, "value": value}]})
        fetched = await pending
        assert fetched.title == "Lunch" and e.client.mirror.get({"record": "Conversation", "id": "c2"}).version == 3
        none = asyncio.ensure_future(vt.docs.fetch(relay.Conversation, "c3"))
        await asyncio.sleep(0)
        e.client.receive({"t": "fetched", "id": e.out[-1]["id"], "documents": []})
        return await none

    assert play(relay.app, body) is None


async def _later(conversation_id: str) -> None:
    await asyncio.sleep(0.01)
    conv = vt.docs[relay.Conversation, conversation_id]
    conv.messages.append(relay.Message(author=relay.User(id="u2", name="Grace"), text="Later."))


async def start_later(ctx, conv: relay.Conversation):
    asyncio.get_running_loop().create_task(_later(conv.id))
    return vt.stay()


def test_work_a_handler_leaves_running_is_confirmed_never_tentative():
    app = vt.app("later", entry="t", tapes=[vt.tape("t", [vt.frame("Wait", shows=relay.Conversation, actions=[vt.action("Later", start_later)])])])

    async def body(e):
        await e.ask({"t": "decide", "id": "1", "handler": "start_later", "session": "s1", "user": ADA, "documents": {"conv": conversation()}})
        await asyncio.sleep(0.05)
        return [m for m in e.out if m["t"] == "sync"]

    [sync] = play(app, body)
    assert "decision" not in sync
    [op] = sync["changes"][0]["ops"]
    assert op["op"] == "insert" and op["value"]["text"]["blocks"][0]["spans"][0]["text"] == "Later." and op["key"].startswith("~")
    assert KEY not in op["value"]
