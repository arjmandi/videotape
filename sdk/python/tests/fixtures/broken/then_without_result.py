"""then-without-result: a call's continuation takes no result."""

import videotape as vt


class Deal(vt.Record):
    name: str


async def deleted(ctx, d: Deal):
    return vt.stay()


async def ask(ctx, d: Deal):
    return vt.call("confirm", then=deleted)


async def load_deal(ctx) -> Deal: ...


deal = vt.tape("deal", [vt.frame("See one deal", shows=Deal, enter=load_deal, actions=[vt.action("Delete", ask), vt.action("More", vt.jump("more"))])])
confirm = vt.tape("confirm", [vt.frame("Confirm", actions=[vt.action("Yes", vt.done(True))])])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("deals", entry="deal", tapes=[deal, confirm, more])
