"""no-exit: the end frame has no way out."""

import videotape as vt

home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Finish", vt.jump("end"))])])
end = vt.tape("end", [vt.frame("Say thank you")])

app = vt.app("site", entry="home", tapes=[home, end])
