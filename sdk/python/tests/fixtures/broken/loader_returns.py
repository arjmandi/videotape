"""loader-returns: the frame shows an Order; its loader returns a Customer."""

import videotape as vt


class Order(vt.Record):
    total: vt.Money


class Customer(vt.Record):
    name: str


async def load_order(ctx) -> Customer: ...


order = vt.tape("order", [
    vt.frame("See one order", shows=Order, enter=load_order, actions=[vt.action("Back", vt.back())]),
])

app = vt.app("orders", entry="order", tapes=[order])
