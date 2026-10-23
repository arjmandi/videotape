"""06 §9.2, a video platform ("Screening").

The guide's code is kept as written, without postponed annotations. Filled in: service stubs, `Comment`, the
loaders, `unsubscribe`, and the home, search, subscriptions, and channel tapes.
"""

import videotape as vt

# ── filled in: services and records the guide leaves out ──


class _Db:
    async def subscribe(self, user_id, channel_id): ...
    async def unsubscribe(self, user_id, channel_id): ...
    async def comments(self, video_id, after, limit): ...


db = _Db()


class Comment(vt.Record):
    author: str = vt.Field(role="supporting")
    text: vt.RichText


# ── 06 §9.2 ──


class VideoCard(vt.Record):
    id: vt.Id
    thumbnail: vt.Image = vt.Field(role="primary")        # an Image carries its own alt text
    title: str = vt.Field(role="heading")
    channel: str = vt.Field(role="supporting")


class Shelf(vt.Record):
    title: str = vt.Field(role="heading")
    videos: list[VideoCard] = vt.Field(select=vt.jump("watch", video_id=VideoCard.id))


class Home(vt.Record):
    shelves: list[Shelf]                                   # a collection of collections


class Channel(vt.Record):
    id: vt.Id
    name: str
    subscribed: bool = vt.State(False)


class Watch(vt.Record):
    id: vt.Id
    player: vt.Video = vt.Field(role="primary", importance="required")   # the platform's player, on a screen in the world
    title: str = vt.Field(role="heading")
    channel: Channel
    description: vt.RichText = vt.Field(importance="optional")
    up_next: list[VideoCard] = vt.Field(select=vt.jump("watch", video_id=VideoCard.id))
    comments: list[Comment] = vt.Field(importance="optional")


@vt.pages(Watch.comments)
async def comments_page(ctx, w: Watch, cursor: str | None) -> vt.Page[Comment]:
    return vt.Page(*await db.comments(w.id, after=cursor, limit=20))


async def subscribe(ctx, w: Watch):
    w.channel.subscribed = True
    await db.subscribe(ctx.user.id, w.channel.id)
    return vt.stay()


async def unsubscribe(ctx, w: Watch):                             # filled in
    w.channel.subscribed = False
    await db.unsubscribe(ctx.user.id, w.channel.id)
    return vt.stay()


async def play_next(ctx, w: Watch):
    return vt.jump("watch", video_id=w.up_next[0].id)


async def load_watch(ctx, video_id: str) -> Watch: ...                       # filled in


watch = vt.tape("watch", [
    vt.frame("Watch a video and decide what next", address="/watch/{video_id}", public=True,
             shows=Watch, enter=load_watch,
             components=[vt.show(Watch.player, on_ended=play_next),
                         vt.show(Channel.name, role="navigation", press=vt.jump("channel", channel_id=Channel.id))],
             actions=[vt.action("Subscribe", subscribe, hidden=Channel.subscribed),
                      vt.action("Subscribed", unsubscribe, visible=Channel.subscribed)]),
])

# ── filled in: the other tapes ──


async def load_home(ctx) -> Home: ...


home = vt.tape("home", [vt.frame("See what is new", address="/", public=True, shows=Home, enter=load_home)])


class VideoSearch(vt.Record):
    q: str = vt.Field(kind="search", commit="change", label="Search videos")


class Found(vt.Record):
    videos: list[VideoCard] = vt.Field([], select=vt.jump("watch", video_id=VideoCard.id))


async def search_videos(ctx, s: VideoSearch, found: Found):
    return vt.stay()


search = vt.tape("search", [
    vt.frame("Find a video", shows=Found, edit=VideoSearch, on_change={VideoSearch.q: search_videos}),
])


class Subscriptions(vt.Record):
    channels: list[Channel] = vt.Field(select=vt.jump("channel", channel_id=Channel.id))


async def load_subscriptions(ctx) -> Subscriptions: ...


subscriptions = vt.tape("subscriptions", [
    vt.frame("Follow the channels I subscribe to", shows=Subscriptions, enter=load_subscriptions),
])


class ChannelPage(vt.Record):
    name: str = vt.Field(role="heading")
    videos: list[VideoCard] = vt.Field(select=vt.jump("watch", video_id=VideoCard.id))


async def load_channel(ctx, channel_id: str) -> ChannelPage: ...


channel = vt.tape("channel", [
    vt.frame("Visit a channel", address="/channel/{channel_id}", public=True, shows=ChannelPage,
             enter=load_channel),
])

# ── 06 §9.2 ──

app = vt.app("screening", entry=home, tapes=[home, search, subscriptions, watch, channel],
             hub=vt.hub([vt.destination(home, "Home", symbol="house"),
                         vt.destination(search, "Search", symbol="magnifier"),
                         vt.destination(subscriptions, "Subscriptions", symbol="list")]),
             world="screening-room")
