"""The journeys app's next release, for the engine's test of a kept journey across a release (Q73):
the wizard's steps frame is gone, and naming the plan goes straight to its review."""

from __future__ import annotations

import journeys as j

import videotape as vt


async def name_plan(ctx, plan: j.Plan):
    if not plan.title:
        raise vt.Reject("Give the plan a name.")
    return vt.goto("review")


wizard = vt.tape("wizard", [
    vt.frame("Name the plan", id="name", edit=j.Plan, enter=j.load_plan, submit=name_plan, on_change={j.Plan.title: j.save_plan}),
    vt.frame("Review the plan", id="review", shows=j.Summary, enter=j.load_summary, back=False,
             actions=[vt.action("Done", vt.jump("home"), role="primary")]),
])

app = vt.app("journeys", entry=j.welcome, tapes=[j.welcome, j.home, wizard, j.confirm, j.inbox, j.item, j.account],
             keep_journeys=j.app.keep_journeys, hub=j.app.hub)
