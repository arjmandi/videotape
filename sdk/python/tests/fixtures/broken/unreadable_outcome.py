"""unreadable-outcome: a handler names its tape with a variable and declares no @vt.outcomes."""

import videotape as vt


class Note(vt.Record):
    text: str


async def save(ctx, n: Note):
    where = "home"
    return vt.jump(where)


home = vt.tape("home", [vt.frame("Write a note", edit=Note, submit=save, actions=[vt.action("More", vt.jump("more"))])])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("notes", entry="home", tapes=[home, more])
