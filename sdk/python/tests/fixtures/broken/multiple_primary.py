"""multiple-primary: two primary actions on one frame."""

import videotape as vt

home = vt.tape("home", [
    vt.frame("Start here", actions=[vt.action("Save", vt.back(), role="primary"),
                                    vt.action("Share", vt.back(), role="primary")]),
])

app = vt.app("site", entry="home", tapes=[home])
