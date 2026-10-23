"""unknown-frame: a handler goes to a frame its tape does not have."""

import videotape as vt


class Question(vt.Record):
    text: str


async def ask(ctx, q: Question) -> vt.Goto["confirm"]:
    return vt.goto("confirm")


ask_tape = vt.tape("ask", [
    vt.frame("Ask a question", edit=Question, submit=ask, actions=[vt.action("Back", vt.back())]),
])

app = vt.app("questions", entry="ask", tapes=[ask_tape])
