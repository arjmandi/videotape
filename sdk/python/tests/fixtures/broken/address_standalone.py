"""address-standalone: /orders/{order_id} opens the order frame directly, but its loader also needs
coupon, which only the jump from home passes."""

import videotape as vt


class Order(vt.Record):
    total: vt.Money


async def load_order(ctx, order_id: str, coupon: str) -> Order: ...


home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Open", vt.jump("order", order_id="o1", coupon="X"))])])
order = vt.tape("order", [
    vt.frame("See one order", address="/orders/{order_id}", shows=Order, enter=load_order,
             actions=[vt.action("Home", vt.jump(home))]),
])

app = vt.app("orders", entry=home, tapes=[home, order])
