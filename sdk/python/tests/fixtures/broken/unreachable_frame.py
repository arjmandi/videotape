"""unreachable-frame: nothing leads to the lost tape."""

import videotape as vt

home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Back", vt.back())])])
lost = vt.tape("lost", [vt.frame("Wait to be found", actions=[vt.action("Back", vt.back())])])

app = vt.app("site", entry="home", tapes=[home, lost])
