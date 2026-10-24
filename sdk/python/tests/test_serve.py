"""The app protocol's client (05 §6.6, §14), against a fake engine."""

import asyncio
import json
import logging

import pytest

import videotape as vt
from conftest import load_sample
from videotape.serve import AppClient, ProtocolError, serve
from videotape.tracking import KEY

hello = load_sample("hello")
relay = load_sample("relay")

ADA = {"record": "User", "id": "u1", "value": {"id": "u1", "name": "Ada"}}                 # relay's user
HELLO_ADA = {"record": "User", "id": "u1", "value": {"id": "u1", "first_name": "Ada"}}     # hello's


class Engine:
    """Plays the engine's side in memory: sends messages to a client and collects what it says."""

    def __init__(self, app):
        self.out: list[dict] = []
        self.client = AppClient(app, self.out.append)

    async def ask(self, msg: dict) -> dict:
        """Sends one request and waits for its result; everything the client said meanwhile is in `out`."""
        self.client.receive(msg)
        while True:
            await asyncio.sleep(0)
            done = [m for m in self.out if m.get("t") == "result" and m["id"] == msg["id"]]
            if done:
                return done[0]

    def syncs(self) -> list[dict]:
        return [m for m in self.out if m["t"] == "sync"]


def play(app, body):
    async def main():
        e = Engine(app)
        e.client.start()
        e.client.receive({"t": "registered", "app": app.name, "v": 1})
        try:
            return await body(e)
        finally:
            e.client.stop()

    return asyncio.run(main())


def draft(ref="d1", version=0, **value):
    return {"ref": {"record": "Draft", "local": ref}, "version": version, "value": {"text": "", **value}}


def conversation(version=0):
    return {
        "ref": {"record": "Conversation", "id": "c1"}, "version": version,
        "value": {
            "id": "c1", "title": "Launch", "typing": None,
            "messages": [{"author": {"id": "u2", "name": "Grace"}, "text": "Ready when you are.",
                          "sent_at": "2026-10-23T09:00:00Z", "pending": False, KEY: "~e1"}],
        },
    }  # fmt: skip


def test_register_carries_the_intent():
    async def body(e):
        return e.out[0]

    msg = play(hello.app, body)
    assert msg["t"] == "register" and msg["v"] == 1
    assert msg["intent"] == hello.app.intent()
    assert msg["sdk"]["language"] == "python"


def test_load_runs_a_loader_with_the_user_and_the_tape_arguments():
    async def body(e):
        workspace = await e.ask({"t": "load", "id": "1", "loader": "load_workspace", "session": "s1", "user": HELLO_ADA, "args": {}})
        report = await e.ask({"t": "load", "id": "2", "loader": "load_report", "session": "s1", "user": HELLO_ADA, "args": {"project_id": "p7"}})
        return workspace, report

    workspace, report = play(hello.app, body)
    assert workspace["documents"] == [{"record": "Workspace", "value": {"id": "u1", "projects": []}}]
    assert report["documents"][0]["record"] == "Report"
    assert report["documents"][0]["value"]["id"] == "p7"


def test_load_failures_come_back_as_errors():
    async def body(e):
        return await e.ask({"t": "load", "id": "1", "loader": "load_workspace", "session": "s1", "user": None, "args": {}})

    assert play(hello.app, body)["error"]["type"] == "AttributeError"     # ctx.user is None without a sign-in


def test_decide_signs_in_with_the_users_record():
    async def body(e):
        creds = {"ref": {"record": "Credentials", "local": "d1"}, "version": 0, "value": {"username": "ada@example.com", "password": "correct horse"}}
        return await e.ask({"t": "decide", "id": "7", "handler": "sign_in", "session": "s1", "user": None, "documents": {"c": creds}})

    result = play(hello.app, body)
    assert result["outcome"] == {
        "type": "jump", "tape": "workspace",
        "sign_in": {"record": "User", "id": "u1", "value": {"id": "u1", "first_name": "Ada"}},
    }  # fmt: skip


def test_reject_comes_back_and_the_secret_never_does(caplog):
    async def body(e):
        creds = {"ref": {"record": "Credentials", "local": "d1"}, "version": 0, "value": {"username": "ada@example.com", "password": "nope-nope"}}
        result = await e.ask({"t": "decide", "id": "8", "handler": "sign_in", "session": "s1", "user": None, "documents": {"c": creds}})
        return result, e.out

    result, said = play(hello.app, body)
    assert result["reject"] == {"message": "That email and password do not match."}
    assert "nope-nope" not in json.dumps(said)


async def leaky(ctx, c: hello.Credentials):
    if c.password:
        raise RuntimeError(f"cannot sign in {c.username} with {c.password}")
    return vt.stay()


def test_errors_are_scrubbed_of_secrets(caplog):
    app = vt.app("leaky", entry="t", tapes=[vt.tape("t", [vt.frame("Sign in", edit=hello.Credentials, submit=leaky)])])

    async def body(e):
        creds = {"ref": {"record": "Credentials", "local": "d1"}, "version": 0, "value": {"username": "ada", "password": "s3cr3t-value"}}
        return await e.ask({"t": "decide", "id": "9", "handler": "leaky", "session": "s1", "user": None, "documents": {"c": creds}})

    with caplog.at_level(logging.ERROR):
        result = play(app, body)
    assert result["error"] == {"type": "RuntimeError", "message": "cannot sign in ada with ••••"}
    assert "s3cr3t-value" not in caplog.text and "••••" in caplog.text


def test_decide_streams_changes_tentatively_before_the_result():
    async def body(e):
        result = await e.ask({
            "t": "decide", "id": "11", "handler": "send", "session": "s1", "user": ADA,
            "documents": {"conv": conversation(), "draft": draft(text="On my way")},
        })  # fmt: skip
        return result, e.out

    result, said = play(relay.app, body)
    assert result["outcome"] == {"type": "stay"}
    syncs = [m for m in said if m["t"] == "sync"]
    assert [m["decision"] for m in syncs] == ["11", "11"]     # one per turn of the event loop: before and after the service
    first, second = syncs
    assert said.index(second) < said.index(result)
    conv_ops = first["changes"][0]["ops"]
    assert first["changes"][0]["doc"] == {"record": "Conversation", "id": "c1"}
    assert conv_ops[0]["op"] == "insert" and conv_ops[0]["at"] == "end" and conv_ops[0]["value"]["pending"] is True
    assert first["changes"][1] == {"doc": {"record": "Draft", "local": "d1"}, "ops": [{"op": "set", "path": ["text"], "value": ""}]}
    key = conv_ops[0]["key"]
    later = {o["path"][-1]: o["value"] for o in second["changes"][0]["ops"]}
    assert second["changes"][0]["ops"][0]["path"][:2] == ["messages", {"key": key}]
    assert later["pending"] is False and later["sent_at"]


def test_a_handler_that_raises_still_sends_what_it_changed_then_the_error():
    async def body(e):
        result = await e.ask({
            "t": "decide", "id": "12", "handler": "send", "session": "s1", "user": ADA,
            "documents": {"conv": conversation(), "draft": draft(text="fail: on my way")},
        })  # fmt: skip
        return result, e.syncs()

    result, syncs = play(relay.app, body)
    assert result["error"] == {"type": "ConnectionError", "message": "the message service is down"}
    assert len(syncs) == 1 and syncs[0]["decision"] == "12"


def test_an_item_is_found_in_the_document_that_holds_it():
    async def body(e):
        conv = conversation()
        item = {**conv, "path": ["messages", {"key": "~e1"}], "record": "Message"}
        result = await e.ask({
            "t": "decide", "id": "13", "handler": "start_reply", "session": "s1", "user": ADA,
            "documents": {"msg": item, "draft": draft()},
        })  # fmt: skip
        return result, e.syncs()

    result, syncs = play(relay.app, body)
    assert result["outcome"] == {"type": "stay"}
    assert syncs[0]["changes"] == [{"doc": {"record": "Draft", "local": "d1"}, "ops": [{"op": "set", "path": ["text"], "value": "> Ready when you are.\n"}]}]


def test_vt_docs_outside_a_handler_is_confirmed_and_inside_is_tentative():
    async def body(e):
        await relay.deliver("c1", relay.Message(author=relay.User(id="u2", name="Grace"), text="Here."))
        await asyncio.sleep(0)
        return e.syncs()

    [sync] = play(relay.app, body)
    assert "decision" not in sync
    [change] = sync["changes"]
    assert change["doc"] == {"record": "Conversation", "id": "c1"}
    assert change["ops"][0]["op"] == "insert" and change["ops"][0]["value"]["text"]["blocks"][0]["spans"][0]["text"] == "Here."


def test_vt_docs_needs_the_engine():
    with pytest.raises(RuntimeError, match="videotape serve"):
        vt.docs[relay.Conversation, "c1"].messages.append(relay.Message(author=relay.User(id="u2", name="G"), text="x"))
    with pytest.raises(AttributeError, match="can change it but not read"):
        vt.docs[relay.Conversation, "c1"].title
    with pytest.raises(TypeError, match="no vt.Id"):
        vt.docs[relay.Draft, "x"]


def test_page_runs_a_paging_loader():
    async def body(e):
        return await e.ask({"t": "page", "id": "14", "loader": "older_messages", "session": "s1", "user": ADA,
                            "cursor": None, "documents": {"conv": conversation()}})  # fmt: skip

    result = play(relay.app, body)
    [item] = result["page"]["items"]
    assert item["text"]["blocks"][0]["spans"][0]["text"] == "Morning." and item[KEY].startswith("~")
    assert result["page"]["next"] is None


def test_serve_speaks_websockets_to_an_engine():
    from websockets.asyncio.server import serve as ws_serve

    seen: list[dict] = []

    async def engine(ws):
        register = json.loads(await ws.recv())
        seen.append(register)
        await ws.send(json.dumps({"t": "registered", "app": register["intent"]["app"], "v": 1}))
        await ws.send(json.dumps({"t": "load", "id": "1", "loader": "load_chats", "session": "s1", "user": None, "args": {}}))
        seen.append(json.loads(await ws.recv()))
        await ws.close()

    async def main():
        async with ws_serve(engine, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            ready = []
            await asyncio.wait_for(serve(relay.app, f"ws://127.0.0.1:{port}", retry=False, ready=ready.append), 5)
            return ready

    ready = asyncio.run(main())
    assert ready == [{"t": "registered", "app": "relay", "v": 1}]
    assert seen[0]["t"] == "register"
    assert seen[1]["documents"][0]["record"] == "Chats"


def test_serve_stops_when_the_engine_refuses():
    from websockets.asyncio.server import serve as ws_serve

    async def engine(ws):
        await ws.recv()
        await ws.send(json.dumps({"t": "error", "code": "bad_intent", "message": "no"}))
        await ws.close()

    async def main():
        async with ws_serve(engine, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            await asyncio.wait_for(serve(relay.app, f"ws://127.0.0.1:{port}", retry=False), 5)

    with pytest.raises(ProtocolError, match="bad_intent"):
        asyncio.run(main())


class _Stamped(vt.Record):
    text: str
    sent_at: relay.datetime


class _Thread(vt.Record):
    id: vt.Id
    notes: list[_Stamped] = []


async def add_unstamped(ctx, thread: _Thread):
    thread.notes.append({"text": "no time"})
    return vt.stay()


def test_a_handler_that_builds_an_invalid_record_is_told_what_is_missing():
    app = vt.app("unstamped", entry="t", tapes=[vt.tape("t", [vt.frame("Add", shows=_Thread, actions=[vt.action("Add", add_unstamped)])])])

    async def body(e):
        doc = {"ref": {"record": "_Thread", "id": "t1"}, "version": 0, "value": {"id": "t1", "notes": []}}
        return await e.ask({"t": "decide", "id": "1", "handler": "add_unstamped", "session": "s1", "user": None, "documents": {"thread": doc}})

    error = play(app, body)["error"]
    assert error["type"] == "ValidationError"
    assert "_Stamped was created without sent_at" in error["message"]
