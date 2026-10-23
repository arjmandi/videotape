# records.py: 06 §2.2, with the records of the tapes it leaves out (06 §3.2, §5.1).
from datetime import datetime

import videotape as vt


class Credentials(vt.Record):
    username: str
    password: vt.Secret


class User(vt.Record):                                     # filled in: what sign_in= takes
    id: vt.Id
    first_name: str


# ── filled in: reset, workspace, report ──


class ResetRequest(vt.Record):
    email: str


class Project(vt.Record):
    id: vt.Id
    name: str = vt.Field(role="heading")
    status: str = vt.Field(role="status")
    updated: datetime = vt.Field(format="relative-time")


class Workspace(vt.Record):
    id: vt.Id
    projects: list[Project] = vt.Field(select=vt.jump("report", project_id=Project.id))


class Report(vt.Record):
    id: vt.Id
    title: str = vt.Field(role="heading")
    chart: vt.Series
    summary: vt.RichText
