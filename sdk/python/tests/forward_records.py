"""Records written with postponed annotations and forward references, as apps often are."""

from __future__ import annotations

import videotape as vt


class Deal(vt.Record):
    id: str = vt.Field(show=False)
    name: str = vt.Field(role="heading")
    owner: User | None = vt.Field(group="people")
    notes: vt.Text(lines=(3, 12)) | None = vt.Field(importance="optional")
    tags: list[str] | None


class User(vt.Record):
    id: str = vt.Field(show=False)
    name: str
