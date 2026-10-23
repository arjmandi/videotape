# app.py: 06 §2.2 as written, then the tapes it leaves out (reset, workspace), and report (06 §3.2).
# reset has two frames, so each has an id (Q36); the others are one-frame tapes and need none.
from records import Credentials, Report, ResetRequest, Workspace
from services import auth, db, reports

import videotape as vt

landing = vt.tape("landing", [
    vt.frame("Say what Hello is and lead to sign-in", address="/", public=True,
             components=[
                 vt.text("Hello, team.", role="heading"),
                 vt.text("Plans, notes, and decisions in one quiet place.", role="supporting"),
             ],
             actions=[vt.action("Sign in", vt.jump("login"), role="primary")]),
])


async def sign_in(ctx, c: Credentials):
    user = await auth.login(c.username, c.password)
    if user is None:
        raise vt.Reject("That email and password do not match.")
    return vt.jump("workspace", sign_in=user)


login = vt.tape("login", [
    vt.frame("Sign in", title="Welcome back", edit=Credentials, submit=sign_in,
             actions=[vt.action("Forgot your password?", vt.jump("reset"), role="secondary")]),
])


# ── filled in ──


async def request_reset(ctx, r: ResetRequest):
    await auth.send_reset(r.email)
    return vt.goto("sent")


reset = vt.tape("reset", [
    vt.frame("Reset your password", id="ask", edit=ResetRequest, submit=request_reset),
    vt.frame("Say that the link is on its way", id="sent",
             components=[vt.text("Check your email for a link.")],
             actions=[vt.action("Back to sign in", vt.jump("login"))]),
])


async def load_workspace(ctx) -> Workspace:
    return Workspace(id=ctx.user.id, projects=await db.projects(owner=ctx.user.id))


workspace = vt.tape("workspace", [
    vt.frame("See your projects", shows=Workspace, enter=load_workspace),
])


async def load_report(ctx, project_id: str) -> Report:
    return await reports.load(project_id)


report = vt.tape("report", [
    vt.frame("Read one report", address="/projects/{project_id}", shows=Report, enter=load_report,
             actions=[vt.action("All projects", vt.jump("workspace"), role="navigation")]),   # a link opens it as a root
])

app = vt.app("hello", entry=landing, tapes=[landing, login, reset, workspace, report],
             world="studio")
