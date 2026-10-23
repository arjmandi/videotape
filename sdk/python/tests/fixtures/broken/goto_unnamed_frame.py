"""goto-unnamed-frame: a goto reaches a frame by the id derived from its purpose."""

import videotape as vt


class Question(vt.Record):
    text: str


async def ask(ctx, q: Question):
    return vt.goto("confirm")


ask_tape = vt.tape("ask", [
    vt.frame("Ask a question", edit=Question, submit=ask),
    vt.frame("Confirm", actions=[vt.action("Back", vt.back())]),
])

app = vt.app("questions", entry="ask", tapes=[ask_tape])
