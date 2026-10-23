"""not-bool: hidden= names a field that is not a bool."""

import videotape as vt


class Post(vt.Record):
    text: str
    likes: int


async def load_post(ctx) -> Post: ...


post = vt.tape("post", [
    vt.frame("Read a post", shows=Post, enter=load_post,
             actions=[vt.action("Like", vt.stay(), hidden=Post.likes), vt.action("More", vt.jump("more"))]),
])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("posts", entry="post", tapes=[post, more])
