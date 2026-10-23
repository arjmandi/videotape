# services.py: stubs for the services 06 §2.2 imports.
from dataclasses import dataclass

from records import Project, Report

import videotape as vt


@dataclass
class User:
    id: str
    first_name: str

    def public(self) -> dict:
        return {"id": self.id, "first_name": self.first_name}


class Auth:
    async def login(self, username: str, password: str) -> User | None:
        if (username, password) == ("ada@example.com", "correct horse"):
            return User("u1", "Ada")
        return None

    async def send_reset(self, email: str) -> None:
        return None


class Db:
    async def projects(self, owner: str) -> list[Project]:
        return []


class Reports:
    async def load(self, project_id: str) -> Report:
        return Report(id=project_id, title="Q3", chart=vt.Series([], x="week", y="events"), summary="Fine.")


auth, db, reports = Auth(), Db(), Reports()
