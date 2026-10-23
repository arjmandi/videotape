"""06 §9.1, the demo: landing, docs, sign-in, dashboard, report.

The guide's code is kept as written; what it leaves out is filled in below the marked lines:
service stubs, the landing and login tapes (from §2.2), `load_report` (from §5.1), and a way off
the docs page and the report.
"""

from __future__ import annotations

from datetime import datetime

import videotape as vt

# ── filled in: services ──


class _Docs:
    async def page(self, slug): ...
    async def toc(self): ...
    async def search(self, q, limit): ...


class _Db:
    async def activity(self, user_id): ...
    async def projects(self, owner): ...


class _Reports:
    async def load(self, project_id): ...
    async def csv(self, report_id): ...


class _Auth:
    async def login(self, username, password): ...


docs_index, db, reports, auth = _Docs(), _Db(), _Reports(), _Auth()

# ── 06 §9.1 ──


class Entry(vt.Record):
    slug: str = vt.Field(show=False)
    title: str


class Page(vt.Record):
    title: str = vt.Field(role="heading")
    body: vt.RichText
    toc: list[Entry] = vt.Field(role="navigation", select=vt.jump("docs", page=Entry.slug))


class Search(vt.Record):
    q: str = vt.Field(kind="search", label="Search the docs", commit="change", importance="optional")
    results: list[Entry] = vt.Field(role="supporting", select=vt.jump("docs", page=Entry.slug))


async def load_page(ctx, page: str = "intro") -> Page:
    p = await docs_index.page(page)
    return Page(id=page, title=p.title, body=vt.RichText.from_markdown(p.markdown), toc=await docs_index.toc())


async def search_docs(ctx, s: Search) -> vt.Stay:
    s.results = await docs_index.search(s.q, limit=8)
    return vt.stay()


docs = vt.tape("docs", [
    vt.frame("Read one page of the docs", address="/docs/{page}", public=True,
             shows=Page, enter=load_page, edit=Search, on_change={Search.q: search_docs},
             actions=[vt.action("Sign in", vt.jump("login"))]),                    # filled in: a way off
])


class Project(vt.Record):
    id: str = vt.Field(show=False)
    name: str = vt.Field(role="heading")
    status: str = vt.Field(role="status")
    updated: datetime = vt.Field(format="relative-time")


class Dashboard(vt.Record):
    greeting: str = vt.Field(role="heading")
    activity: vt.Series = vt.Field(importance="optional")
    projects: list[Project] = vt.Field(select=vt.jump("report", project_id=Project.id))


async def load_dashboard(ctx) -> Dashboard:
    return Dashboard(id=ctx.user.id,
                     greeting=vt.t("dashboard.hello", name=ctx.user.first_name),
                     activity=vt.Series(await db.activity(ctx.user.id), x="week", y="events"),
                     projects=await db.projects(owner=ctx.user.id))


dashboard = vt.tape("dashboard", [
    vt.frame("See how my projects are doing", address="/projects", shows=Dashboard, enter=load_dashboard),
])


class Report(vt.Record):
    title: str = vt.Field(role="heading")
    chart: vt.Series
    summary: vt.RichText
    exported: str | None = vt.Field(role="status")


async def export_csv(ctx, r: Report) -> vt.Download:
    return vt.download(f"{r.id}.csv", await reports.csv(r.id))


# ── filled in: 06 §5.1 ──


async def load_report(ctx, project_id: str) -> Report:
    return await reports.load(project_id)


report = vt.tape("report", [
    vt.frame("Read one report", address="/projects/{project_id}", shows=Report, enter=load_report,
             actions=[vt.action("Export CSV", export_csv, role="primary"),
                      vt.action("Back to projects", vt.back())]),                    # filled in: a way off
])

# ── filled in: landing and sign-in, from 06 §2.2 ──


class Credentials(vt.Record):
    username: str
    password: vt.Secret


landing = vt.tape("landing", [
    vt.frame("Say what Hello is and lead to sign-in", id="intro", address="/", public=True,
             components=[
                 vt.text("Hello, team.", role="heading"),
                 vt.text("Plans, notes, and decisions in one quiet place.", role="supporting"),
             ],
             actions=[vt.action("Sign in", vt.jump("login"), role="primary"),
                      vt.action("Read the docs", vt.jump("docs", page="intro"))]),
])


async def sign_in(ctx, c: Credentials) -> vt.Jump["dashboard"]:
    user = await auth.login(c.username, c.password)
    if user is None:
        raise vt.Reject("That email and password do not match.")
    return vt.jump("dashboard", sign_in=user.id)


login = vt.tape("login", [
    vt.frame("Sign in", title="Welcome back", edit=Credentials, submit=sign_in),
])

app = vt.app("demo", entry="landing", tapes=[landing, docs, login, dashboard, report], world="studio")
