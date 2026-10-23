"""unknown-argument: a select passes colour, which the target's loader does not take."""

import videotape as vt


class Order(vt.Record):
    id: str = vt.Field(show=False)
    total: vt.Money


class Orders(vt.Record):
    orders: list[Order] = vt.Field(select=vt.jump("order", order_id=Order.id, colour="red"))


async def load_order(ctx, order_id: str) -> Order: ...


orders = vt.tape("orders", [vt.frame("See my orders", shows=Orders)])
order = vt.tape("order", [
    vt.frame("See one order", shows=Order, enter=load_order, actions=[vt.action("More", vt.jump("more"))]),
])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("orders", entry="orders", tapes=[orders, order, more])
