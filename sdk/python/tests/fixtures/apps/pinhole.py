"""06 §9.3, a photo-sharing app ("Pinhole").

The guide's code is kept as written. Filled in: service stubs, `feed_page` (defined before `Feed`,
which names it), the loaders, `unlike`, the story handlers, a way into stories, and the explore,
activity, profile, and post tapes, with a hub.
"""

import videotape as vt

# ── filled in: services ──


class _Db:
    async def like(self, user_id, post_id): ...
    async def unlike(self, user_id, post_id): ...
    async def feed(self, user_id, after, limit): ...


db = _Db()

# ── 06 §9.3 ──


class Author(vt.Record):
    id: str = vt.Field(show=False)
    name: str
    avatar: vt.Image


class Post(vt.Record):
    id: str = vt.Field(show=False)
    author: Author = vt.Field(press=vt.jump("profile", user_id=Author.id))
    photo: vt.Image = vt.Field(role="primary")
    liked: bool = vt.State(False)
    likes: int = vt.Field(format="count")
    caption: vt.RichText                                   # mentions and hashtags are links


async def like(ctx, post: Post) -> vt.Stay:
    post.liked, post.likes = True, post.likes + 1          # on screen now; rolled back if the call fails
    await db.like(ctx.user.id, post.id)
    return vt.stay()


async def unlike(ctx, post: Post) -> vt.Stay:                                 # filled in
    post.liked, post.likes = False, post.likes - 1
    await db.unlike(ctx.user.id, post.id)
    return vt.stay()


async def feed_page(ctx, cursor: str | None) -> vt.Page[Post]:                 # filled in: 06 §5.5
    posts, next_cursor = await db.feed(ctx.user.id, after=cursor, limit=20)
    return vt.Page(posts, next=next_cursor)


class Feed(vt.Record):
    posts: list[Post] = vt.Field(pages=feed_page)


async def load_feed(ctx) -> Feed: ...                                         # filled in


feed = vt.tape("feed", [
    vt.frame("See what people I follow posted", shows=Feed, enter=load_feed, actions=[
        vt.action("Like", like, on=Post, gesture="double-tap", hidden=Post.liked),
        vt.action("Liked", unlike, on=Post, visible=Post.liked),
        vt.action("Comments", vt.jump("post", post_id=Post.id), on=Post),
        vt.action("Stories", vt.jump("stories")),                                 # filled in: a way in
    ]),
])


class Story(vt.Record):
    picture: vt.Image = vt.Field(role="primary")
    who: str = vt.Field(role="supporting")


async def load_story(ctx, index: int = 0) -> Story: ...                        # filled in


async def next_story(ctx, s: Story) -> vt.Jump["stories"] | vt.Back:         # filled in
    return vt.back()


async def previous_story(ctx, s: Story) -> vt.Jump["stories"]:                 # filled in
    return vt.jump("stories")


stories = vt.tape("stories", [
    vt.frame("Watch one story", shows=Story, enter=load_story,
             actions=[vt.action("Next", next_story, gesture="tap-trailing"),
                      vt.action("Previous", previous_story, gesture="tap-leading")],
             after=vt.after(seconds=5, then=next_story)),
])

# ── filled in: the other tapes ──


class Explore(vt.Record):
    posts: list[Post] = vt.Field(select=vt.jump("post", post_id=Post.id))


async def load_explore(ctx) -> Explore: ...


explore = vt.tape("explore", [vt.frame("Discover posts", shows=Explore, enter=load_explore)])


class Reaction(vt.Record):
    who: str
    what: str
    post_id: str = vt.Field(show=False)


class Activity(vt.Record):
    reactions: list[Reaction] = vt.Field(select=vt.jump("post", post_id=Reaction.post_id))


async def load_activity(ctx) -> Activity: ...


activity = vt.tape("activity", [vt.frame("See who reacted", shows=Activity, enter=load_activity)])


class Profile(vt.Record):
    name: str = vt.Field(role="heading")
    avatar: vt.Image
    posts: list[Post] = vt.Field(select=vt.jump("post", post_id=Post.id))


async def load_profile(ctx, user_id: str) -> Profile: ...


profile = vt.tape("profile", [
    vt.frame("Look at someone", address="/u/{user_id}", public=True, shows=Profile, enter=load_profile),
])


class Comment(vt.Record):
    author: Author
    text: vt.RichText


class PostPage(vt.Record):
    post: Post
    comments: list[Comment]


async def load_post(ctx, post_id: str) -> PostPage: ...


post = vt.tape("post", [
    vt.frame("Read one post and what people said", address="/p/{post_id}", public=True,
             shows=PostPage, enter=load_post),
])

app = vt.app("pinhole", entry="feed", tapes=[feed, explore, activity, profile, stories, post],
             hub=vt.hub([vt.destination("feed", "Feed", symbol="house"),
                         vt.destination("explore", "Explore", symbol="magnifier"),
                         vt.destination("activity", "Activity", symbol="heart")]),
             world="darkroom")
