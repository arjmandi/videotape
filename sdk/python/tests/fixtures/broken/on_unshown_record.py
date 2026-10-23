"""on-unshown-record: an action is on= a record the frame does not show."""

import videotape as vt


class Post(vt.Record):
    text: str


class Comment(vt.Record):
    text: str


class Feed(vt.Record):
    posts: list[Post]


feed = vt.tape("feed", [
    vt.frame("See what people posted", shows=Feed,
             actions=[vt.action("Hide", vt.stay(), on=Comment), vt.action("Back", vt.back())]),
])

app = vt.app("feed", entry="feed", tapes=[feed])
