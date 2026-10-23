"""Records written with postponed annotations and forward references, as apps often are."""

from __future__ import annotations

import videotape as vt


class Deal(vt.Record):
    id: vt.Id
    name: str = vt.Field(role="heading")
    owner: User | None = vt.Field(group="people")
    notes: vt.Text | None = vt.Field(lines=(3, 12), importance="optional")
    tags: list[str] | None


class User(vt.Record):
    id: vt.Id
    name: str
