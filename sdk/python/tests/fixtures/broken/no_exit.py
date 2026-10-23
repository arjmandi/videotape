"""no-exit: the end frame says back=False and has no other way out."""

import videotape as vt

home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Finish", vt.jump("end"))])])
end = vt.tape("end", [vt.frame("Say thank you", back=False)])

app = vt.app("site", entry="home", tapes=[home, end])
