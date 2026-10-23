"""unknown-frame: a handler goes to a frame its tape does not have."""

import videotape as vt


class Question(vt.Record):
    text: str


async def ask(ctx, q: Question):
    return vt.goto("confirm")


ask_tape = vt.tape("ask", [
    vt.frame("Ask a question", edit=Question, submit=ask, actions=[vt.action("More", vt.jump("more"))]),
])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("questions", entry="ask", tapes=[ask_tape, more])
