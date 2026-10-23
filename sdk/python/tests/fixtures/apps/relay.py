"""06 §9.4, a chat app ("Relay"), with the app line from 06 §3.4.

The guide's code is kept as written, except `Message.sent_at`, which is optional here: the guide's
`send` builds a `Message` before the service has given it a time, and a required `sent_at` refuses
that. Filled in: fake services (an in-memory store, with an outage for messages that start with
"fail:"), `User`, the loaders, and the chats, contacts, and settings tapes. The engine's tests play
this app (packages/engine).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import videotape as vt

# ── filled in: services and records ──


class User(vt.Record):
    id: vt.Id
    name: str


class _Db:
    """An in-memory message service: two users, two conversations."""

    def __init__(self) -> None:
        self.users = {"u1": User(id="u1", name="Ada"), "u2": User(id="u2", name="Grace")}
        self.titles = {"c1": "Launch", "c2": "Lunch"}
        self.sent: dict[str, list[tuple[str, str, datetime]]] = {"c1": [("u2", "Ready when you are.", datetime(2026, 10, 23, 9, 0))], "c2": []}
        self.older = {"c1": [("u2", "Morning.", datetime(2026, 10, 23, 8, 0))]}

    async def send(self, conversation_id, user_id, text):
        await asyncio.sleep(0.001)                        # a network hop: the message is pending meanwhile
        plain = text.plain if isinstance(text, vt.RichText) else str(text)
        if plain.startswith("fail:"):
            raise ConnectionError("the message service is down")
        sent_at = datetime.now(timezone.utc)
        self.sent[conversation_id].append((user_id, plain, sent_at))
        return {"sent_at": sent_at}

    async def messages(self, conversation_id, before, limit):
        rows = self.older.get(conversation_id, []) if before is None else []
        return [Message(author=self.users[u], text=t, sent_at=at) for u, t, at in rows][:limit], None

    def conversation(self, conversation_id: str) -> "Conversation":
        msgs = [Message(author=self.users[u], text=t, sent_at=at) for u, t, at in self.sent[conversation_id]]
        return Conversation(id=conversation_id, title=self.titles[conversation_id], messages=msgs)


db = _Db()


# ── 06 §9.4 ──


class Message(vt.Record):
    author: User
    text: vt.RichText
    sent_at: datetime | None = vt.Field(format="time", importance="optional")   # optional here: see above
    pending: bool = vt.State(False)


class Conversation(vt.Record):
    id: vt.Id
    title: str = vt.Field(role="heading")
    messages: list[Message] = vt.Field(anchor="end")
    typing: str | None = vt.Field(role="status", importance="optional")


class Draft(vt.Record):
    text: vt.Text = ""


@vt.pages(Conversation.messages)
async def older_messages(ctx, conv: Conversation, cursor: str | None) -> vt.Page[Message]:
    return vt.Page(*await db.messages(conv.id, before=cursor, limit=50))


async def send(ctx, conv: Conversation, draft: Draft):
    msg = conv.messages.append(Message(author=ctx.user, text=draft.text, pending=True))
    draft.text = ""                                       # both on screen now, in every session showing conv
    msg.update(await db.send(conv.id, ctx.user.id, msg.text), pending=False)
    return vt.stay()


async def start_reply(ctx, msg: Message, draft: Draft):
    draft.text = f"> {msg.text.plain}\n"
    return vt.stay()


async def load_thread(ctx, id: str) -> Conversation:                         # filled in
    return db.conversation(id)


thread = vt.tape("thread", [
    vt.frame("Read and reply", shows=Conversation, edit=Draft, submit=vt.action("Send", send),
             address="/c/{id}", enter=load_thread, actions=[
                 vt.action("Reply", start_reply, on=Message, gesture="swipe-trailing"),
                 vt.action("Copy", vt.copy(Message.text), on=Message),
             ]),
])


async def deliver(conversation_id: str, msg: Message):    # your service calls this when a message arrives
    vt.docs[Conversation, conversation_id].messages.append(msg)


# ── filled in: the other tapes ──


class ConversationSummary(vt.Record):
    id: vt.Id
    title: str = vt.Field(role="heading")
    last: str | None = vt.Field(role="supporting")
    unread: bool = vt.State(False)


class Chats(vt.Record):
    conversations: list[ConversationSummary] = vt.Field(select=vt.jump("thread", id=ConversationSummary.id))


async def load_chats(ctx) -> Chats:
    return Chats(conversations=[ConversationSummary(id=c, title=t) for c, t in db.titles.items()])


chats = vt.tape("chats", [vt.frame("See my conversations", shows=Chats, enter=load_chats)])


class Contact(vt.Record):
    id: vt.Id
    name: str
    conversation: str = vt.Field(show=False)


class Contacts(vt.Record):
    contacts: list[Contact] = vt.Field(select=vt.jump("thread", id=Contact.conversation))


async def load_contacts(ctx) -> Contacts:
    return Contacts(contacts=[Contact(id="u2", name="Grace", conversation="c1")])


contacts = vt.tape("contacts", [vt.frame("Find someone to talk to", shows=Contacts, enter=load_contacts)])


class Settings(vt.Record):
    display_name: str
    notifications: bool = True


async def save_settings(ctx, s: Settings):
    return vt.stay()


async def load_settings(ctx) -> Settings:
    return Settings(display_name=ctx.user.name if ctx.user else "")


settings = vt.tape("settings", [
    vt.frame("Change my settings", edit=Settings, enter=load_settings, submit=save_settings),
])

# ── 06 §3.4 ──

app = vt.app("relay", entry=chats, tapes=[chats, thread, contacts, settings],
             hub=vt.hub([vt.destination(chats, "Chats", symbol="chat"),
                         vt.destination(contacts, "Contacts", symbol="person"),
                         vt.destination(settings, "Settings", symbol="gear")]))
