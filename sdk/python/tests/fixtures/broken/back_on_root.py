"""back-on-root: the entry frame offers back, and nothing ever enters it with history."""

import videotape as vt

home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Go back", vt.back()),
                                                         vt.action("More", vt.jump("more"))])])
more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("site", entry="home", tapes=[home, more])
