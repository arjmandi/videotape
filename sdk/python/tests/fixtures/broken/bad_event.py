"""bad-event: on_ended= on a field that is text, not media."""

import videotape as vt


class Post(vt.Record):
    title: str


async def next_post(ctx, p: Post) -> vt.Stay:
    return vt.stay()


post = vt.tape("post", [
    vt.frame("Read a post", shows=Post, components=[vt.show(Post.title, on_ended=next_post)],
             actions=[vt.action("Back", vt.back())]),
])

app = vt.app("posts", entry="post", tapes=[post])
