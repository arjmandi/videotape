"""A small app for the engine's journey tests: every kind of edge, history roots, and the hub.

welcome (the entry, no hub) signs in to home, a hub destination; inbox and account are the others.
home jumps into a three-frame wizard whose frames share one draft and the tape's arguments, and
calls a confirmation whose result reaches a then= handler. inbox selects an item, which also opens
by its address (under inbox). account signs out back to welcome.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import videotape as vt


class Person(vt.Record):
    id: vt.Id
    name: str


class Login(vt.Record):
    name: str
    password: vt.Secret


class Home(vt.Record):
    id: vt.Id
    greeting: str
    visits: int = 0


class Plan(vt.Record):
    title: str = vt.Field("", max_length=20)
    steps: int = vt.Field(1, ge=1, le=9)


class Summary(vt.Record):
    topic: str
    text: str


class Question(vt.Record):
    text: str = "Are you sure?"


class Item(vt.Record):
    id: vt.Id
    title: str


class Inbox(vt.Record):
    id: vt.Id
    items: list[Item] = vt.Field(select=vt.jump("item", item_id=Item.id))


# ── welcome ──


PEOPLE = {"Ada": "p1", "Grace": "p2"}


async def sign_in(ctx, login: Login):
    if login.password != "pw":
        raise vt.Reject("Wrong password.")
    return vt.jump("home", sign_in=Person(id=PEOPLE.get(login.name, "p0"), name=login.name))


async def sign_in_here(ctx, login: Login):
    if login.password != "pw":
        raise vt.Reject("Wrong password.")
    return vt.jump("home", sign_in=Person(id=PEOPLE.get(login.name, "p0"), name=login.name), resume=False)


welcome = vt.tape("welcome", [
    vt.frame("Sign in", edit=Login, submit=sign_in, actions=[vt.action("Sign in here", sign_in_here)]),
])


# ── home ──


async def load_home(ctx) -> Home:
    return Home(id=f"home-{ctx.user.id}", greeting=f"Hello, {ctx.user.name}")


async def ask(ctx):
    return vt.call("confirm", then=answered)


async def answered(ctx, home: Home, result: bool):
    home.greeting = "Confirmed" if result else "Kept"
    return vt.stay()


async def wave(ctx, home: Home):
    home.visits += 1
    return vt.stay()


async def overdo(ctx, home: Home):
    home.visits += 10
    if home.visits > 5:
        raise vt.Reject("Too much waving.")
    return vt.stay()


async def _wave_soon(home_id: str) -> None:
    await asyncio.sleep(0.02)
    vt.docs[Home, home_id].visits += 1                 # after the decision: the app's own change (Q54)


async def wave_later(ctx, home: Home):
    asyncio.get_running_loop().create_task(_wave_soon(home.id))
    return vt.stay()


async def export(ctx, home: Home):
    return vt.download("home.txt", home.greeting)


home = vt.tape("home", [
    vt.frame("See home", shows=Home, enter=load_home, actions=[
        vt.action("Plan something", vt.jump("wizard", topic="garden"), role="primary"),
        vt.action("Confirm", ask),
        vt.action("Wave", wave),
        vt.action("Wave too much", overdo),
        vt.action("Wave later", wave_later),
        vt.action("Export", export),
        vt.action("Help", vt.open("https://example.com/help")),
        vt.action("Copy greeting", vt.copy(Home.greeting)),
    ]),
])


# ── the wizard: three frames, one draft, the tape's arguments ──


async def name_plan(ctx, plan: Plan):
    if not plan.title:
        raise vt.Reject("Give the plan a name.")
    return vt.goto("steps")


async def count_steps(ctx, plan: Plan):
    return vt.goto("review")


async def load_summary(ctx, topic: str, plan: Plan) -> Summary:
    return Summary(topic=topic, text=f"{plan.title} in {plan.steps} steps")


wizard = vt.tape("wizard", [
    vt.frame("Name the plan", id="name", edit=Plan, submit=name_plan),
    vt.frame("Count the steps", id="steps", edit=Plan, submit=vt.action("Next", count_steps)),
    vt.frame("Review the plan", id="review", shows=Summary, enter=load_summary, back=False,
             actions=[vt.action("Done", vt.jump("home"), role="primary")]),
])


# ── a call ──

confirm = vt.tape("confirm", [
    vt.frame("Confirm", shows=Question, actions=[
        vt.action("Yes", vt.done(True), role="primary"),
        vt.action("No", vt.done(False)),
    ]),
])


# ── inbox and its items ──


async def load_inbox(ctx) -> Inbox:
    return Inbox(id=f"inbox-{ctx.user.id}", items=[Item(id="i1", title="First"), Item(id="i2", title="Second")])


inbox = vt.tape("inbox", [vt.frame("See the inbox", shows=Inbox, enter=load_inbox)])


async def load_item(ctx, item_id: str) -> Item:
    return Item(id=item_id, title=f"Item {item_id}")


item = vt.tape("item", [
    vt.frame("Read an item", shows=Item, enter=load_item, address="/items/{item_id}", hub=False),
])


# ── account ──


async def sign_out(ctx):
    return vt.jump("welcome", sign_out=True)


account = vt.tape("account", [vt.frame("Your account", actions=[vt.action("Sign out", sign_out)])])


app = vt.app("journeys", entry=welcome, tapes=[welcome, home, wizard, confirm, inbox, item, account],
             keep_journeys=timedelta(days=7),
             hub=vt.hub([vt.destination(home, "Home"), vt.destination(inbox, "Inbox"),
                         vt.destination(account, "Account")]))
