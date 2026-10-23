"""missing-argument: the jump into the order tape passes order_id, but its second frame's loader
also needs coupon; arguments belong to the tape, and goto carries none (Q46)."""

import videotape as vt


class Order(vt.Record):
    total: vt.Money


class Discount(vt.Record):
    percent: int = 0


async def load_order(ctx, order_id: str) -> Order: ...


async def load_discount(ctx, order: Order, coupon: str) -> Discount: ...   # the order from the first frame


home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Latest order", vt.jump("order", order_id="o1"))])])
order = vt.tape("order", [
    vt.frame("See one order", id="see", shows=Order, enter=load_order,
             actions=[vt.action("Discount", vt.goto("discount"))]),
    vt.frame("See the discount", id="discount", shows=Discount, enter=load_discount),
])

app = vt.app("orders", entry="home", tapes=[home, order])
