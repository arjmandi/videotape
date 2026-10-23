"""bad-under: a linked thread names settings beneath it, but settings never reaches the thread."""

import videotape as vt


class Thread(vt.Record):
    id: vt.Id
    title: str


async def load_thread(ctx, id: str) -> Thread: ...


chats = vt.tape("chats", [vt.frame("See my chats", actions=[vt.action("Open", vt.jump("thread", id="c1"))])])
settings = vt.tape("settings", [vt.frame("Change my settings")])
thread = vt.tape("thread", [
    vt.frame("Read a thread", address="/c/{id}", shows=Thread, enter=load_thread, under=settings),
])

app = vt.app("chat", entry=chats, tapes=[chats, settings, thread],
             hub=vt.hub([vt.destination(chats, "Chats"), vt.destination(settings, "Settings")]))
