"""unknown-entry: the app's entry names no tape."""

import videotape as vt

home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("More", vt.jump("more"))])])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("lost", entry="start", tapes=[home, more])
