"""Handlers written with postponed annotations, before the records they name."""

from __future__ import annotations

import videotape as vt


async def confirm(ctx, order: Order) -> vt.Goto["done"] | vt.Jump["orders"] | vt.Back:
    return vt.back()


async def pick(ctx, order: Order) -> vt.Call["pick_address"]:
    return vt.call("pick_address")


async def nameless(ctx, order: Missing) -> vt.Stay:  # noqa: F821 - Missing is never defined
    return vt.stay()


class Order(vt.Record):
    id: str = vt.Field(show=False)
    total: vt.Money
