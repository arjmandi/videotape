"""missing-argument: an action jumps to a tape whose loader needs order_id, without it."""

import videotape as vt


class Order(vt.Record):
    total: vt.Money


async def load_order(ctx, order_id: str) -> Order: ...


home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Latest order", vt.jump("order"))])])
order = vt.tape("order", [
    vt.frame("See one order", shows=Order, enter=load_order, actions=[vt.action("Back", vt.back())]),
])

app = vt.app("orders", entry="home", tapes=[home, order])
