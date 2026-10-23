"""public-without-address: a public frame with no address to serve it at."""

import videotape as vt

home = vt.tape("home", [vt.frame("Say what we do", public=True, actions=[vt.action("Back", vt.back())])])

app = vt.app("site", entry="home", tapes=[home])
