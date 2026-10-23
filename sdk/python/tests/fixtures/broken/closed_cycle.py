"""closed-cycle: once in a, the journey goes between a and b forever."""

import videotape as vt

home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Go", vt.jump("a"))])])
a = vt.tape("a", [vt.frame("See A", actions=[vt.action("To B", vt.jump("b"))])])
b = vt.tape("b", [vt.frame("See B", actions=[vt.action("To A", vt.jump("a"))])])

app = vt.app("loop", entry="home", tapes=[home, a, b])
