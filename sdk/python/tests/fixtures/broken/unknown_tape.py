"""unknown-tape: an action and a handler's return type name a tape that does not exist."""

import videotape as vt


class Note(vt.Record):
    text: str


async def save(ctx, n: Note):
    return vt.jump("notes")


home = vt.tape("home", [
    vt.frame("Write a note", edit=Note, submit=save,
             actions=[vt.action("Settings", vt.jump("settings")), vt.action("More", vt.jump("more"))]),
])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("notes", entry="home", tapes=[home, more])
