"""not-bool: hidden= names a field that is not a bool."""

import videotape as vt


class Post(vt.Record):
    text: str
    likes: int


post = vt.tape("post", [
    vt.frame("Read a post", shows=Post,
             actions=[vt.action("Like", vt.stay(), hidden=Post.likes), vt.action("Back", vt.back())]),
])

app = vt.app("posts", entry="post", tapes=[post])
