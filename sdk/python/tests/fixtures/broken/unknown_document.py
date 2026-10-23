"""unknown-document: a handler takes a record its frame neither shows nor edits."""

import videotape as vt


class Note(vt.Record):
    text: str


class User(vt.Record):
    name: str


async def save(ctx, n: Note, u: User) -> vt.Stay:
    return vt.stay()


home = vt.tape("home", [vt.frame("Write a note", edit=Note, submit=save, actions=[vt.action("Back", vt.back())])])

app = vt.app("notes", entry="home", tapes=[home])
