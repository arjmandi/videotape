"""ambiguous-record: on=Entry, where the frame holds Entry in both Page.toc and Search.results."""

import videotape as vt


class Entry(vt.Record):
    slug: vt.Id
    title: str


class Page(vt.Record):
    title: str
    toc: list[Entry]


class Search(vt.Record):
    q: str = vt.Field(kind="search", commit="change")
    results: list[Entry]


async def find(ctx, s: Search):
    return vt.stay()


docs = vt.tape("docs", [
    vt.frame("Read the docs", shows=Page, edit=Search, on_change={Search.q: find},
             actions=[vt.action("Open", vt.jump("docs"), on=Entry),             # which Entry?
                      vt.action("Read", vt.jump("docs"), on=Page.toc),          # this one is fine
                      vt.action("Back", vt.back())]),
])

app = vt.app("docs", entry="docs", tapes=[docs])
