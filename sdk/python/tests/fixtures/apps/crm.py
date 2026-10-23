"""06 §9.5, a CRM ("Pipeline"), with `Stage` and `Deal` from 06 §4 and `export_csv` from 06 §6.

The guide's code is kept as written. Filled in: service stubs, `Company`, `User`, `team`,
`Companies`, `Search`, `Contact`, the loaders, `search_companies`, and the deal, contacts, and
contact tapes, with a hub.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

import videotape as vt

# ── filled in: services and records ──


class _Db:
    async def move(self, deal_id, stage, by): ...
    async def create(self, deal, by): ...


class _Reports:
    async def csv(self, pipeline_id): ...


db, reports = _Db(), _Reports()


class Company(vt.Record):
    id: vt.Id
    name: str = vt.Field(role="heading")


class User(vt.Record):
    id: vt.Id
    name: str


async def team(ctx) -> list[User]: ...


# ── 06 §4 ──


class Stage(Enum):
    LEAD = "lead"; QUALIFIED = "qualified"; PROPOSAL = "proposal"; WON = "won"  # noqa: E702


class Deal(vt.Record):
    id: vt.Id
    name: str = vt.Field(role="heading")
    company: Company = vt.pick("pick_company")            # a call that returns a Company
    amount: vt.Money = vt.Field(ge=0)
    stage: Stage                                          # a choice
    close: date | None = vt.Field(group="dates")
    owner: User = vt.Field(group="people", options=team)
    notes: vt.Text | None = vt.Field(lines=(3, 12), importance="optional")


# ── 06 §9.5 ──


class Pipeline(vt.Record):
    id: vt.Id
    deals: list[Deal] = vt.Field(group_by=Deal.stage, select=vt.jump("deal", deal_id=Deal.id))
    forecast: vt.Series = vt.Field(importance="optional")
    can_export: bool = vt.State(False)


async def move_deal(ctx, deal: Deal, to: Stage) -> vt.Stay:
    deal.stage = to
    moved = await db.move(deal.id, to, by=ctx.user.id)
    vt.docs[Pipeline, moved.team].deals.replace(moved)
    return vt.stay()


async def export_csv(ctx, p: Pipeline) -> vt.Download:                         # 06 §6
    return vt.download("pipeline.csv", await reports.csv(p.id))


async def load_pipeline(ctx) -> Pipeline: ...                                 # filled in


deals = vt.tape("deals", [
    vt.frame("See every open deal by stage and move them on", shows=Pipeline, enter=load_pipeline,
             actions=[
                 vt.action("Move to stage", move_deal, on=Deal, to=Stage, gesture="drag"),
                 vt.action("New deal", vt.jump("new_deal"), role="primary", key="n"),
                 vt.action("Export CSV", export_csv, visible=Pipeline.can_export, importance="optional"),
             ]),
])


async def create_deal(ctx, d: Deal) -> vt.Jump["deals"]:
    saved = await db.create(d, by=ctx.user.id)
    vt.docs[Pipeline, saved.team].deals.append(saved)
    return vt.jump("deals")


new_deal = vt.tape("new_deal", [vt.frame("Create a deal", edit=Deal, submit=create_deal)])

# ── filled in: what pick_company shows ──


class Companies(vt.Record):
    companies: list[Company]


class Search(vt.Record):
    q: str = vt.Field(kind="search", commit="change", importance="optional")


async def load_companies(ctx) -> Companies: ...


async def search_companies(ctx, s: Search, c: Companies) -> vt.Stay:
    return vt.stay()


# ── 06 §9.5 ──

pick_company = vt.tape("pick_company", [
    vt.frame("Pick a company", shows=Companies, enter=load_companies,
             edit=Search, on_change={Search.q: search_companies},
             actions=[vt.action("Choose", vt.done(Company), on=Company)]),
])

# ── filled in: Contact ──


class Contact(vt.Record):
    id: vt.Id
    name: str = vt.Field(role="heading")
    company: str
    email: str


# ── 06 §9.5 ──


class Contacts(vt.Record):
    contacts: list[Contact] = vt.Field(surface=True, select=vt.jump("contact", contact_id=Contact.id))   # a table, even on a phone


# ── filled in: the other tapes ──


async def load_contacts(ctx) -> Contacts: ...


contacts = vt.tape("contacts", [vt.frame("Find a contact", shows=Contacts, enter=load_contacts)])


class Touch(vt.Record):
    when: date
    what: vt.RichText


class ContactPage(vt.Record):
    contact: Contact
    history: list[Touch]


async def load_contact(ctx, contact_id: str) -> ContactPage: ...


contact = vt.tape("contact", [
    vt.frame("Review a contact's history", address="/contacts/{contact_id}", shows=ContactPage,
             enter=load_contact),
])


async def load_deal(ctx, deal_id: str) -> Deal: ...


deal = vt.tape("deal", [
    vt.frame("See one deal", address="/deals/{deal_id}", shows=Deal, enter=load_deal,
             actions=[vt.action("Back to the board", vt.back())]),
])

app = vt.app("pipeline", entry="deals", tapes=[deals, deal, new_deal, pick_company, contacts, contact],
             hub=vt.hub([vt.destination("deals", "Deals", symbol="board"),
                         vt.destination("contacts", "Contacts", symbol="person")]),
             world="quiet-office")
