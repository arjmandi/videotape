"""unreadable-record: a record names a type that is never defined."""

from __future__ import annotations

import videotape as vt


class Order(vt.Record):
    lines: list[Line]  # noqa: F821 - Line is never defined


app = vt.app("shop", entry="orders", tapes=[
    vt.tape("orders", [vt.frame("See an order", shows=Order, actions=[vt.action("Back", vt.back())])]),
])
