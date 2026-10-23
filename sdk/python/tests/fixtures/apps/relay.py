"""06 §9.4, a chat app ("Relay"), with the app line from 06 §3.4.

The guide's code is kept as written. Filled in: service stubs, `User`, `older_messages` (defined
before `Conversation`, which names it), `load_thread`, and the chats, contacts, and settings tapes.
The module-level `vt.docs[...]` line becomes a function, since it runs when a message arrives.
"""

from __future__ import annotations

from datetime import datetime

import videotape as vt

# ── filled in: services and records ──


class _Db:
    async def send(self, conversation_id, user_id, text): ...


db = _Db()


class User(vt.Record):
    id: str = vt.Field(show=False)
    name: str


async def older_messages(ctx, cursor: str | None) -> vt.Page[Message]:
    return vt.Page([], next=None)


# ── 06 §9.4 ──


class Message(vt.Record):
    author: User
    text: vt.RichText
    sent_at: datetime = vt.Field(format="time", importance="optional")
    pending: bool = vt.State(False)


class Conversation(vt.Record):
    title: str = vt.Field(role="heading")
    messages: list[Message] = vt.Field(anchor="end", pages=older_messages)
    typing: str | None = vt.Field(role="status", importance="optional")


class Draft(vt.Record):
    text: vt.Text(lines=(1, 6)) = ""


async def send(ctx, conv: Conversation, draft: Draft) -> vt.Stay:
    msg = conv.messages.append(Message(author=ctx.user, text=draft.text, pending=True))
    draft.text = ""                                       # both on screen now, in every session showing conv
    msg.update(await db.send(conv.id, ctx.user.id, msg.text), pending=False)
    return vt.stay()


async def start_reply(ctx, msg: Message, draft: Draft) -> vt.Stay:
    draft.text = f"> {msg.text.plain}\n"
    return vt.stay()


async def load_thread(ctx, id: str) -> Conversation: ...                     # filled in


thread = vt.tape("thread", [
    vt.frame("Read and reply", shows=Conversation, edit=Draft, submit=send,
             address="/c/{id}", enter=load_thread, actions=[
                 vt.action("Reply", start_reply, on=Message, gesture="swipe-trailing"),
                 vt.action("Copy", vt.copy(Message.text), on=Message),
             ]),
])


# when a message arrives from anyone, anywhere in your app process
def on_incoming(msg):
    vt.docs[Conversation, msg.conversation_id].messages.append(msg)


# ── filled in: the other tapes ──


class ConversationSummary(vt.Record):
    id: str = vt.Field(show=False)
    title: str = vt.Field(role="heading")
    last: str | None = vt.Field(role="supporting")
    unread: bool = vt.State(False)


class Chats(vt.Record):
    conversations: list[ConversationSummary] = vt.Field(select=vt.jump("thread", id=ConversationSummary.id))


async def load_chats(ctx) -> Chats: ...


chats = vt.tape("chats", [vt.frame("See my conversations", shows=Chats, enter=load_chats)])


class Contact(vt.Record):
    id: str = vt.Field(show=False)
    name: str
    conversation: str = vt.Field(show=False)


class Contacts(vt.Record):
    contacts: list[Contact] = vt.Field(select=vt.jump("thread", id=Contact.conversation))


async def load_contacts(ctx) -> Contacts: ...


contacts = vt.tape("contacts", [vt.frame("Find someone to talk to", shows=Contacts, enter=load_contacts)])


class Settings(vt.Record):
    display_name: str
    notifications: bool = True


async def save_settings(ctx, s: Settings) -> vt.Stay:
    return vt.stay()


async def load_settings(ctx) -> Settings: ...


settings = vt.tape("settings", [
    vt.frame("Change my settings", edit=Settings, enter=load_settings, submit=save_settings),
])

# ── 06 §3.4 ──

app = vt.app("relay", entry="chats", tapes=[chats, thread, contacts, settings],
             hub=vt.hub([vt.destination("chats", "Chats", symbol="chat"),
                         vt.destination("contacts", "Contacts", symbol="person"),
                         vt.destination("settings", "Settings", symbol="gear")]))
