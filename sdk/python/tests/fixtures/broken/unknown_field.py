"""unknown-field: vt.show names a field of a record the frame does not have."""

import videotape as vt


class Customer(vt.Record):
    name: str


class Order(vt.Record):
    total: vt.Money


order = vt.tape("order", [
    vt.frame("See one order", shows=Order, components=[vt.show(Customer.name, role="heading")],
             actions=[vt.action("Back", vt.back())]),
])

app = vt.app("orders", entry="order", tapes=[order])
