"""unreachable-frame: nothing leads to the lost tape."""

import videotape as vt

home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("More", vt.jump("more"))])])
lost = vt.tape("lost", [vt.frame("Wait to be found", actions=[vt.action("More", vt.jump("more"))])])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("site", entry="home", tapes=[home, lost, more])
