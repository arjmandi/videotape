# services.py: stubs for the services 06 §2.2 imports.
from records import Project, Report, User

import videotape as vt


class Auth:
    async def login(self, username: str, password: str) -> User | None:
        if (username, password) == ("ada@example.com", "correct horse"):
            return User(id="u1", first_name="Ada")
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
