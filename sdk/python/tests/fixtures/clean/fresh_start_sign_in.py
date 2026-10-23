"""Q51, the side that is not reported: after a sign-in, dashboard and a linked report form a group
with no way out (no sign-out, and the report's link makes it a root), but the group holds the
sign-in target, so it is the app the user came for, not a trap."""

import videotape as vt


class Report(vt.Record):
    id: vt.Id
    title: str


class User(vt.Record):
    id: vt.Id
    name: str


async def sign_in(ctx):
    return vt.jump("dashboard", sign_in=User(id="u1", name="Ada"))


async def load_report(ctx, report_id: str) -> Report: ...


landing = vt.tape("landing", [vt.frame("Welcome", actions=[vt.action("Sign in", sign_in)])])
dashboard = vt.tape("dashboard", [
    vt.frame("See my reports", actions=[vt.action("Q3", vt.jump("report", report_id="q3"))]),
])
report = vt.tape("report", [
    vt.frame("Read one report", address="/reports/{report_id}", shows=Report, enter=load_report,
             actions=[vt.action("All reports", vt.jump("dashboard"), role="navigation")]),
])

app = vt.app("reports", entry=landing, tapes=[landing, dashboard, report])
