"""Q51, the side that is not reported: a plain jump leads from the landing into the hub, and the
hub's part of the app has no way back to the landing, but it holds the hub's destinations, so it
is the app, not a trap."""

import videotape as vt

landing = vt.tape("landing", [vt.frame("Welcome", actions=[vt.action("Enter", vt.jump("home"))])])
home = vt.tape("home", [vt.frame("See home", back=False, actions=[vt.action("Detail", vt.jump("detail"))])])
detail = vt.tape("detail", [vt.frame("See a detail", back=False)])
settings = vt.tape("settings", [vt.frame("Change settings")])

app = vt.app("hubbed", entry=landing, tapes=[landing, home, detail, settings],
             hub=vt.hub([vt.destination(home, "Home"), vt.destination(settings, "Settings")]))
