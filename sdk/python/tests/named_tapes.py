"""Handlers that name tapes by module constants and tape objects (Q45)."""

import videotape as vt

DASHBOARD = "dashboard"


class Tapes:
    settings = "settings"


dashboard = vt.tape("dashboard", [vt.frame("See the dashboard")])


async def by_constant(ctx):
    return vt.jump(DASHBOARD)


async def by_tape(ctx):
    return vt.jump(dashboard, week=1)


async def by_dotted_name(ctx):
    return vt.call(Tapes.settings)


async def by_local(ctx):
    DASHBOARD = "elsewhere"  # noqa: N806 - shadows the constant on purpose
    return vt.jump(DASHBOARD)


async def goto_with_arguments(ctx):
    return vt.goto("confirm", step=2)
