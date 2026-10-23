"""address-param: the address passes order_id; the loader takes id."""

import videotape as vt


class Order(vt.Record):
    total: vt.Money


async def load_order(ctx, id: str) -> Order: ...


order = vt.tape("order", [
    vt.frame("See one order", address="/orders/{order_id}", shows=Order, enter=load_order,
             actions=[vt.action("More", vt.jump("more"))]),
])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("orders", entry="order", tapes=[order, more])
