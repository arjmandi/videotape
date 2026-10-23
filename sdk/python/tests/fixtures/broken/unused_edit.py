"""unused-edit: a frame edits a Note, and nothing receives it."""

import videotape as vt


class Note(vt.Record):
    text: str


home = vt.tape("home", [vt.frame("Write a note", edit=Note, actions=[vt.action("More", vt.jump("more"))])])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("notes", entry="home", tapes=[home, more])
