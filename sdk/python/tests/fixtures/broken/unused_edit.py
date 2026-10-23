"""unused-edit: a frame edits a Note, and nothing receives it."""

import videotape as vt


class Note(vt.Record):
    text: str


home = vt.tape("home", [vt.frame("Write a note", edit=Note, actions=[vt.action("Back", vt.back())])])

app = vt.app("notes", entry="home", tapes=[home])
