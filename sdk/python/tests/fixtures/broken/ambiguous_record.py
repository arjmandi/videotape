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


async def load_page(ctx) -> Page: ...


docs = vt.tape("docs", [
    vt.frame("Read the docs", shows=Page, enter=load_page, edit=Search, on_change={Search.q: find},
             actions=[vt.action("Open", vt.jump("more"), on=Entry),             # which Entry?
                      vt.action("Read", vt.jump("more"), on=Page.toc),          # this one is fine
                      vt.action("More", vt.jump("more"))]),
])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("docs", entry="docs", tapes=[docs, more])
