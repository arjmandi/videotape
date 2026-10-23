"""edited-select: search results kept in the record the frame edits, with select=."""

import videotape as vt


class Entry(vt.Record):
    slug: vt.Id
    title: str


class Search(vt.Record):
    q: str = vt.Field(kind="search", commit="change")
    results: list[Entry] = vt.Field([], select=vt.jump("more"))     # shown data, in the edited record


async def find(ctx, s: Search):
    return vt.stay()


docs = vt.tape("docs", [
    vt.frame("Search the docs", edit=Search, on_change={Search.q: find}, actions=[vt.action("More", vt.jump("more"))]),
])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("docs", entry="docs", tapes=[docs, more])
