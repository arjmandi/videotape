"""done-without-call: the confirm tape ends with done, but home jumps to it instead of calling it."""

import videotape as vt

home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Confirm", vt.jump("confirm"))])])
confirm = vt.tape("confirm", [
    vt.frame("Confirm", actions=[vt.action("Yes", vt.done(True)), vt.action("Home", vt.jump("home"))]),
])

app = vt.app("uncalled", entry="home", tapes=[home, confirm])
