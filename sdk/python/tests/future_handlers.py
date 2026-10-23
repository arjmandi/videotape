"""Handlers written with postponed annotations, before the records they name."""

from __future__ import annotations

import videotape as vt


async def confirm(ctx, order: Order):
    if order.total > 100:
        return vt.goto("done")
    return vt.jump("orders", order_id=order.id) if order.id else vt.back()


async def pick(ctx, order: Order):
    return vt.call("pick_address", then=address_picked, order_id=order.id)


async def address_picked(ctx, order: Order, result: str):
    return vt.stay()


async def nameless(ctx, order: Missing):  # noqa: F821 - Missing is never defined
    return vt.stay()


class Order(vt.Record):
    id: vt.Id
    total: vt.Money
