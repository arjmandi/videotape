"""unknown-entry: the app's entry names no tape."""

import videotape as vt

home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Back", vt.back())])])

app = vt.app("lost", entry="start", tapes=[home])
