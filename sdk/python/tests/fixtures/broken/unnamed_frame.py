"""unnamed-frame: a tape of two frames whose first has no id=."""

import videotape as vt


class Question(vt.Record):
    text: str


async def ask(ctx, q: Question):
    return vt.goto("confirm")


ask_tape = vt.tape("ask", [
    vt.frame("Ask a question", edit=Question, submit=ask),
    vt.frame("Confirm", id="confirm"),
])

app = vt.app("questions", entry="ask", tapes=[ask_tape])
