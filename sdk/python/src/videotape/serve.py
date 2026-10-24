"""The app protocol's client (05 §6.6, §14): the app process connects out to the engine.

    videotape serve app:app --engine ws://127.0.0.1:8787/app

It sends `register` with the intent, then answers the engine: `load` runs an enter loader, `page`
a list's paging loader, and `decide` a handler, as `vt.invoke` does. Requests name documents by
reference and version, and the client hands handlers its mirror's copies (`videotape.mirror`),
answering `stale` when a copy is missing or behind. While a handler runs, every change it makes is
sent at once as a `sync` delta, tentative under that decision; the decision's `result` confirms
them, and an error or a `Reject` rolls them back. Changes made outside a decision (`vt.docs[...]`
from a service, or work a handler left running) are confirmed at once (Q54). Secrets reach the
handler once and are never sent back or logged: the SDK scrubs them from errors and forwarded log
lines. The message shapes are written down in `packages/engine/README.md`.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sys
import traceback
from collections.abc import Callable
from typing import Any

from pydantic import TypeAdapter

from ._encode import encode
from .decisions import Context, Reject, call, read
from .mirror import Mirror, mirrorable
from .outcomes import Outcome
from .records import Record, fields_of, id_field
from .serialize import build
from .tracking import KEY, Tracker, current, dump, key_of, keys_scope, known_key, load

PROTOCOL = 1
SDK_VERSION = "0.0.1"
MASK = "••••"

log = logging.getLogger("videotape.serve")


class ProtocolError(Exception):
    """The engine refused the app, or said something the client cannot follow."""


def find_record(name: str, modules: set[str] = frozenset()) -> type[Record] | None:  # type: ignore[assignment]
    """A record class by name among every record defined in the process, preferring those defined in
    `modules` (the app's own)."""
    queue: list[type[Record]] = list(Record.__subclasses__())
    seen: set[type] = set()
    found: list[type[Record]] = []
    while queue:
        cls = queue.pop(0)
        if cls in seen:
            continue
        seen.add(cls)
        if cls.__name__ == name:
            found.append(cls)
        queue.extend(cls.__subclasses__())
    found.sort(key=lambda c: c.__module__ not in modules)
    return found[0] if found else None


def _walk(value: Any, path: list[Any]) -> Any:
    """The object at `path` inside a tracked record: field names, and `{"key": ...}` for list items."""
    for seg in path:
        if isinstance(seg, dict):
            value = next((v for v in value if isinstance(v, Record) and known_key(v) == seg.get("key")), None)
        else:
            value = getattr(value, seg, None)
        if value is None:
            return None
    return value


class AppClient:
    """The app's side of the protocol, transport-free: `receive` takes each message from the engine,
    and `send` (given) takes each message for it, in order."""

    def __init__(self, app: Any, send: Callable[[dict[str, Any]], None]) -> None:
        built = build(app)
        self.app = app
        self.intent = built.intent
        self.handlers = built.handlers
        self.loaders = built.loaders
        self.send = send
        self.registered: asyncio.Future[dict[str, Any]] | None = None
        self.tasks: set[asyncio.Task[Any]] = set()
        self.secrets: set[str] = set()
        """Secret values of the decisions running now; every error and log line is scrubbed of them."""
        self.records: dict[str, type[Record]] = {r.__name__: r for r in built.records}
        """Records by name: the app's own first, then the user's record once a sign-in names it."""
        functions = [*self.handlers.values(), *self.loaders.values()]
        self.modules = {getattr(f, "__module__", "") for f in functions} | {r.__module__ for r in built.records}
        self.outside: Tracker | None = None
        """Changes made outside any decision (`vt.docs` from a service), confirmed at once."""
        self.mirror = Mirror(self.record, self._forget)
        self.running = 0
        self.fetches: dict[str, asyncio.Future[None]] = {}
        self._fetched = 0

    # ── connection ──

    def start(self) -> None:
        loop = asyncio.get_running_loop()
        self.registered = loop.create_future()
        self.outside = Tracker(self._sync, None)
        self.outside.on_local = self.mirror.sent
        global client
        client = self
        self.send({"t": "register", "v": PROTOCOL, "intent": self.intent, "sdk": {"language": "python", "version": SDK_VERSION}})

    def stop(self) -> None:
        global client
        if client is self:
            client = None
        for task in list(self.tasks):
            task.cancel()
        self.mirror.clear()

    def receive(self, msg: dict[str, Any]) -> None:
        t = msg.get("t")
        if t == "registered":
            if self.registered is not None and not self.registered.done():
                self.registered.set_result(msg)
        elif t == "error":
            error = ProtocolError(f"{msg.get('code')}: {msg.get('message')}")
            if self.registered is not None and not self.registered.done():
                self.registered.set_exception(error)
            else:
                log.error("the engine says %s", error)
        elif t in ("load", "decide", "page"):
            stale = self._prepare(msg)
            if stale:
                self.send({"t": "result", "id": msg["id"], "stale": stale})
                return
            task = asyncio.ensure_future(self._answer(msg))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        elif t == "sync":
            for change in msg.get("changes") or []:
                self.mirror.apply(change)
            for ref in msg.get("drop") or []:
                self.mirror.drop(ref)
        elif t == "fetched":
            for doc in msg.get("documents") or []:
                self.mirror.adopt(doc["doc"], doc["value"], doc["version"])
            future = self.fetches.pop(msg.get("id", ""), None)
            if future is not None and not future.done():
                future.set_result(None)
        elif t == "pong":
            pass
        else:
            log.warning("ignoring a message the client does not know: %s", t)

    # ── answering ──

    def _prepare(self, msg: dict[str, Any]) -> list[dict[str, Any]]:
        """Takes the documents a request sends whole into the mirror, and says which of those it names
        by version the mirror does not hold at that version. Runs as the request arrives, before any
        later `sync` can move a copy on."""
        stale = []
        for entry in (msg.get("documents") or {}).values():
            record = self.record(entry["ref"].get("record", ""))
            if record is None or not mirrorable(record):
                continue
            if "value" in entry:
                self.mirror.adopt(entry["ref"], entry["value"], entry["version"])
                continue
            copy = self.mirror.get(entry["ref"])
            if copy is None or copy.version != entry["version"]:
                stale.append({"doc": entry["ref"], "have": copy.version if copy else None})
        return stale

    def _document(self, entry: dict[str, Any], record: type[Record] | None, tracker: Tracker | None) -> Any:
        """What a handler or loader receives for one entry (`record` is what it receives: the item's
        record for an item): the mirror's copy, or the item in it at `path`; or, where the document's
        record is one the mirror never holds, a record of its own."""
        container = self.record(entry["ref"].get("record", ""))
        if container is not None and mirrorable(container):
            copy = self.mirror.get(entry["ref"])
            if copy is None:
                raise ProtocolError(f"the app holds no copy of {entry['ref']}")
            found = _walk(copy.obj, entry.get("path") or [])
            if found is None:
                raise ProtocolError(f"no item at {entry.get('path')} in {entry['ref']}")
            return found
        if record is None:
            return entry.get("value")
        if tracker is not None:
            return tracker.adopt(record, entry["value"], entry["ref"], entry.get("path") or ())
        return load(record, entry["value"])

    async def fetch(self, refs: list[dict[str, Any]]) -> None:
        """Asks the engine for documents the app does not hold (`await vt.docs.fetch(...)`)."""
        self._fetched += 1
        key = f"f{self._fetched}"
        future = asyncio.get_running_loop().create_future()
        self.fetches[key] = future
        self.send({"t": "fetch", "id": key, "docs": refs})
        await future

    def _forget(self, refs: list[dict[str, Any]]) -> None:
        self.send({"t": "forget", "docs": refs})

    async def _answer(self, msg: dict[str, Any]) -> None:
        secrets = self._secrets_in(msg)
        self.secrets |= secrets
        self.running += 1
        try:
            with keys_scope():
                if msg["t"] == "decide":
                    reply = await self._decide(msg)
                elif msg["t"] == "load":
                    reply = await self._load(msg)
                else:
                    reply = await self._page(msg)
        except Exception as e:  # noqa: BLE001 - every failure of app code goes back as an error result
            text = "\n".join([str(e), *getattr(e, "__notes__", [])])
            reply = {"error": {"type": type(e).__name__, "message": self.scrub(text)[:8000]}}
            log.error("%s %s raised %s", msg["t"], msg.get("handler") or msg.get("loader"), self.scrub(_trace(e)))
        finally:
            self.secrets -= secrets
            self.running -= 1
            if self.running == 0:
                self.mirror.release_retired()
        self.send({"t": "result", "id": msg["id"], **reply})

    def _ctx(self, msg: dict[str, Any]) -> Context:
        user = msg.get("user")
        if not user:
            return Context(user=None)
        cls = self.record(user["record"])
        return Context(user=load(cls, user["value"]) if cls else user["value"])

    def record(self, name: str) -> type[Record] | None:
        """A record by name: the app's own, then any record the process defines."""
        known = self.records.get(name)
        if known is None:
            known = find_record(name, self.modules)
            if known is not None:
                self.records[name] = known
        return known

    def _record(self, annotation: Any, name: str | None) -> type[Record] | None:
        if isinstance(annotation, type) and issubclass(annotation, Record):
            return annotation
        return self.record(name) if name else None

    async def _decide(self, msg: dict[str, Any]) -> dict[str, Any]:
        handler = self.handlers.get(msg["handler"])
        if handler is None:
            raise ProtocolError(f"the app has no handler {msg['handler']}")
        sig = read(handler)
        tracker = Tracker(self._sync, msg["id"])
        tracker.on_local = self.mirror.sent
        token = current.set(tracker)
        try:
            kwargs: dict[str, Any] = {}
            for name, entry in (msg.get("documents") or {}).items():
                p = sig.param(name)
                record = self._record(p.annotation if p else None, entry.get("record") or entry["ref"].get("record"))
                if record is None:
                    raise ProtocolError(f"{msg['handler']}() takes {name}, whose record the app does not have")
                kwargs[name] = self._document(entry, record, tracker)
            kwargs.update(msg.get("values") or {})
            try:
                outcome = await call(handler, self._ctx(msg), **kwargs)
            except Reject as r:
                tracker.flush()
                return {"reject": {"message": _json(r.message)}}
            tracker.flush()
            return {"outcome": self._outcome(outcome)}
        finally:
            current.reset(token)
            tracker.close()

    def _outcome(self, outcome: Outcome) -> dict[str, Any]:
        out = outcome.to_json()
        user = getattr(outcome, "sign_in", None)
        if isinstance(user, Record):
            self.records[type(user).__name__] = type(user)
            ident = id_field(type(user))
            out["sign_in"] = {"record": type(user).__name__, "id": str(getattr(user, ident)), "value": dump(user)}
        return out

    async def _arguments(self, fn: Callable[..., Any], msg: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        sig = read(fn)
        kwargs: dict[str, Any] = {}
        args = msg.get("args") or {}
        documents = msg.get("documents") or {}
        for p in sig.params:
            if p.name in extra:
                kwargs[p.name] = extra[p.name]
            elif p.name in documents:
                entry = documents[p.name]
                kwargs[p.name] = self._document(entry, self._record(p.annotation, entry["ref"].get("record")), None)
            elif p.name in args:
                raw = args[p.name]
                kwargs[p.name] = raw if p.annotation is inspect.Parameter.empty else TypeAdapter(p.annotation).validate_python(raw)
        return kwargs

    async def _load(self, msg: dict[str, Any]) -> dict[str, Any]:
        loader = self.loaders.get(msg["loader"])
        if loader is None:
            raise ProtocolError(f"the app has no loader {msg['loader']}")
        result = loader(self._ctx(msg), **await self._arguments(loader, msg, {}))
        if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
            result = await result
        values = result if isinstance(result, tuple) else (result,)
        documents = []
        for value in values:
            if isinstance(value, Record):
                documents.append({"record": type(value).__name__, "value": dump(value)})
            elif isinstance(value, list) and all(isinstance(v, Record) for v in value):
                item = type(value[0]).__name__ if value else None
                documents.append({"collection": item, "value": [{**dump(v), KEY: key_of(v)} for v in value]})
            else:
                raise TypeError(f"{msg['loader']}() returned {type(value).__name__}, not a document")
        return {"documents": documents}

    async def _page(self, msg: dict[str, Any]) -> dict[str, Any]:
        loader = self.loaders.get(msg["loader"])
        if loader is None:
            raise ProtocolError(f"the app has no loader {msg['loader']}")
        result = loader(self._ctx(msg), **await self._arguments(loader, msg, {"cursor": msg.get("cursor")}))
        if asyncio.iscoroutine(result):
            result = await result
        items = [{**dump(v), KEY: key_of(v)} if isinstance(v, Record) else _json(v) for v in result.items]
        return {"page": {"items": items, "next": result.next}}

    # ── documents and secrets ──

    def _sync(self, changes: list[dict[str, Any]], decision: str | None) -> None:
        msg: dict[str, Any] = {"t": "sync", "changes": changes}
        if decision is not None:
            msg["decision"] = decision
        self.send(msg)

    def _secrets_in(self, msg: dict[str, Any]) -> set[str]:
        """The secret values a decision's documents carry, so nothing the app says repeats them."""
        found: set[str] = set()
        for value in (msg.get("documents") or {}).values():
            record = self.record(value.get("ref", {}).get("record", ""))
            if record is None or not isinstance(value.get("value"), dict):
                continue
            for spec in fields_of(record):
                secret = value["value"].get(spec.name) if spec.kind.type == "secret" else None
                if isinstance(secret, str) and secret:
                    found.add(secret)
        return found

    def scrub(self, text: str) -> str:
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, MASK)
        return text


def _json(value: Any) -> Any:
    return encode(value)


def _trace(e: BaseException) -> str:
    return "".join(traceback.format_exception(type(e), e, e.__traceback__)).rstrip()


client: AppClient | None = None
"""The client of this process while it serves, for `vt.docs`."""


# ── logs ─────────────────────────────────────────────────────────────────────


class ForwardLogs(logging.Handler):
    """Sends the app's log lines to the engine as `log`, scrubbed of the secrets in play."""

    LEVELS = {logging.DEBUG: "debug", logging.INFO: "info", logging.WARNING: "warning", logging.ERROR: "error"}

    def __init__(self, client: AppClient) -> None:
        super().__init__(logging.INFO)
        self.client = client

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(("websockets", "asyncio"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = self.LEVELS.get(record.levelno, "error" if record.levelno > logging.ERROR else "info")
            message = self.client.scrub(record.getMessage())
            self.client.send({"t": "log", "level": level, "message": message, "logger": record.name})
        except Exception:  # noqa: BLE001 - a log line must never take the app down
            self.handleError(record)


# ── the transport ────────────────────────────────────────────────────────────


async def serve(app: Any, engine: str, *, retry: bool = True, ready: Callable[[dict[str, Any]], None] | None = None) -> None:
    """Connects to the engine at `engine` (a ws:// or wss:// URL) and serves the app until the
    connection ends; with `retry`, reconnects with backoff when the engine goes away."""
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed

    delay = 0.25
    while True:
        try:
            async with connect(engine, max_size=16 * 2**20) as ws:
                delay = 0.25
                await _session(app, ws, ready)
        except ProtocolError:
            raise
        except (OSError, ConnectionClosed) as e:
            if not retry:
                raise
            log.warning("engine unreachable (%s); retrying in %.1fs", e, delay)
        if not retry:
            return
        await asyncio.sleep(delay)
        delay = min(delay * 2, 5.0)


async def _session(app: Any, ws: Any, ready: Callable[[dict[str, Any]], None] | None) -> None:
    out: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    c = AppClient(app, out.put_nowait)
    forward = ForwardLogs(c)
    root = logging.getLogger()
    root.addHandler(forward)

    async def writer() -> None:
        while True:
            msg = await out.get()
            await ws.send(json.dumps(msg, ensure_ascii=False))

    w = asyncio.create_task(writer())
    try:
        c.start()

        async def reader() -> None:
            async for raw in ws:
                c.receive(json.loads(raw))

        r = asyncio.create_task(reader())
        assert c.registered is not None
        done, _ = await asyncio.wait({r, c.registered}, return_when=asyncio.FIRST_COMPLETED)
        if c.registered in done:
            info = c.registered.result()
            if ready is not None:
                ready(info)
        await r
    finally:
        root.removeHandler(forward)
        c.stop()
        w.cancel()
        if c.registered is not None and c.registered.done() and c.registered.exception() is not None:
            raise c.registered.exception()  # type: ignore[misc]


def main(target: Any, engine: str, retry: bool) -> int:
    """`videotape serve`: serves `target` (an App) until interrupted."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(name)s %(levelname)s %(message)s")
    logging.getLogger("websockets").setLevel(logging.WARNING)

    def ready(info: dict[str, Any]) -> None:
        print(f"videotape: serving {info.get('app')} to {engine}", file=sys.stderr, flush=True)

    try:
        asyncio.run(serve(target, engine, retry=retry, ready=ready))
    except ProtocolError as e:
        print(f"videotape: the engine refused the app: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    except OSError as e:
        print(f"videotape: cannot reach the engine at {engine}: {e}", file=sys.stderr)
        return 2
    return 0

