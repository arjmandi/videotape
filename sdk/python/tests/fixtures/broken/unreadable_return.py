"""unreadable-return: a handler without a return type, so its edges are unknown."""

import videotape as vt


class Note(vt.Record):
    text: str


async def save(ctx, n: Note):
    return vt.stay()


home = vt.tape("home", [vt.frame("Write a note", edit=Note, submit=save, actions=[vt.action("Back", vt.back())])])

app = vt.app("notes", entry="home", tapes=[home])
