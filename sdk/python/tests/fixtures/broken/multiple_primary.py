"""multiple-primary: two primary actions on one frame."""

import videotape as vt

home = vt.tape("home", [
    vt.frame("Start here", actions=[vt.action("Save", vt.jump("more"), role="primary"),
                                    vt.action("Share", vt.jump("more"), role="primary")]),
])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("site", entry="home", tapes=[home, more])
