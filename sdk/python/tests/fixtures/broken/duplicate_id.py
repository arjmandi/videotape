"""duplicate-id: two frames share an address, and two different handlers share a name."""

import videotape as vt


class Note(vt.Record):
    text: str


async def save(ctx, n: Note):
    return vt.jump("b")


first = vt.tape("a", [vt.frame("Write a note", address="/notes", edit=Note, submit=save)])


async def save(ctx, n: Note):  # noqa: F811 - the mistake under test
    return vt.back()


second = vt.tape("b", [vt.frame("Write another note", address="/notes", edit=Note, submit=save)])

app = vt.app("notes", entry="a", tapes=[first, second])
