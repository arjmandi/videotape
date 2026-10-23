"""hidden-required: the form edits a Deal whose required owner_id is hidden."""

import videotape as vt


class Deal(vt.Record):
    id: vt.Id                                   # not required until saved: fine
    name: str
    owner_id: str = vt.Field(show=False)        # required and hidden: the form can never be complete


async def create(ctx, d: Deal):
    return vt.jump("done")


new = vt.tape("new", [vt.frame("Create a deal", edit=Deal, submit=create)])
done = vt.tape("done", [vt.frame("Say the deal exists")])

app = vt.app("deals", entry="new", tapes=[new, done])
